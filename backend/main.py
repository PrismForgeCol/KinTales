import os
from typing import Optional, Dict, Any
from fastapi import FastAPI, BackgroundTasks, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
from dotenv import load_dotenv
import httpx
import uuid
import google.generativeai as genai
import json

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")
RUNPOD_IMAGE_ENDPOINT_ID = os.getenv("RUNPOD_IMAGE_ENDPOINT_ID")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL")  # e.g., https://your-ngrok-url.ngrok.io
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

app = FastAPI(title="KinTales Backend API")

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class GenerateRequest(BaseModel):
    prompt: str
    character_id: Optional[str] = None # If linking to a specific character
    user_id: Optional[str] = None # Linking to the logged-in user

class GenerateResponse(BaseModel):
    status: str
    id: str

@app.get("/")
def read_root():
    return {"message": "KinTales API is running"}

@app.post("/api/generate", response_model=GenerateResponse)
async def generate_image(req: GenerateRequest):
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    if not RUNPOD_API_KEY or not RUNPOD_IMAGE_ENDPOINT_ID:
        raise HTTPException(status_code=500, detail="RunPod not configured")

    # Generate a unique ID for this request
    generation_id = str(uuid.uuid4())

    # 1. Log request to database
    try:
        supabase.table("image_generations").insert({
            "id": generation_id,
            "prompt": req.prompt,
            "character_id": req.character_id,
            "user_id": req.user_id,
            "status": "processing"
        }).execute()
    except Exception as e:
        print(f"Error inserting into Supabase: {e}")
        raise HTTPException(status_code=500, detail="Database error")

    # 2. Trigger RunPod AI
    webhook_url = f"{WEBHOOK_BASE_URL}/api/webhook/{generation_id}"
    runpod_url = f"https://api.runpod.ai/v2/{RUNPOD_IMAGE_ENDPOINT_ID}/run"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {RUNPOD_API_KEY}"
    }

    payload = {
        "input": {
            "prompt": req.prompt,
            # Additional model-specific parameters can go here
        },
        "webhook": webhook_url
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(runpod_url, json=payload, headers=headers)
            response.raise_for_status()
            runpod_data = response.json()
            runpod_job_id = runpod_data.get("id")
            
            # Optionally update DB with RunPod Job ID
            supabase.table("image_generations").update({
                "runpod_job_id": runpod_job_id
            }).eq("id", generation_id).execute()

        except Exception as e:
            print(f"Error calling RunPod: {e}")
            # Mark as failed in DB
            supabase.table("image_generations").update({
                "status": "failed"
            }).eq("id", generation_id).execute()
            raise HTTPException(status_code=500, detail="Error triggering image generation")

    return GenerateResponse(status="processing", id=generation_id)

@app.post("/api/webhook/{generation_id}")
async def runpod_webhook(generation_id: str, request: Request):
    if not supabase:
        return {"status": "error", "message": "Supabase not configured"}

    payload = await request.json()
    print(f"Received webhook for {generation_id}: {payload}")

    # RunPod webhook payload typically contains 'status' and 'output'
    status = payload.get("status")
    
    if status == "COMPLETED":
        # Extract the image URL(s) from output. This structure depends on the specific RunPod worker
        output = payload.get("output", {})
        image_url = None
        
        # Example structures: output might be a URL directly, a list, or a dict
        if isinstance(output, dict) and "image_url" in output:
            image_url = output["image_url"]
        elif isinstance(output, list) and len(output) > 0:
            image_url = output[0] # Assuming first item is URL
        elif isinstance(output, str):
            image_url = output
            
        if image_url:
            final_url = image_url
            try:
                image_data = None
                if image_url.startswith('http'):
                    async with httpx.AsyncClient() as dl_client:
                        img_resp = await dl_client.get(image_url)
                        if img_resp.status_code == 200:
                            image_data = img_resp.content
                elif image_url.startswith('data:image'):
                    import base64
                    header, b64 = image_url.split(',', 1)
                    image_data = base64.b64decode(b64)
                
                if image_data:
                    file_name = f"generated/{generation_id}.png"
                    supabase.storage.from_("images").upload(
                        path=file_name,
                        file=image_data,
                        file_options={"content-type": "image/png"}
                    )
                    final_url = supabase.storage.from_("images").get_public_url(file_name)
            except Exception as e:
                print(f"Error uploading image to Supabase Storage: {e}")
                # Fall back to original url if upload fails

            supabase.table("image_generations").update({
                "status": "completed",
                "image_url": final_url
            }).eq("id", generation_id).execute()
        else:
            supabase.table("image_generations").update({
                "status": "failed_no_image"
            }).eq("id", generation_id).execute()
            
    elif status in ["FAILED", "CANCELLED"]:
        supabase.table("image_generations").update({
            "status": "failed"
        }).eq("id", generation_id).execute()

    return {"status": "ok"}

class AnalyzeImageRequest(BaseModel):
    image_base64: str
    mime_type: str

@app.post("/api/analyze-image")
async def analyze_image(req: AnalyzeImageRequest):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API not configured")

    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        
        system_instruction = "Task: Generate a highly detailed visual description from the pictures. Make sure to capture:\n1) What type of character the picture is mainly about to include: Type: human, animal, if animal what kind of animal is it. If human: try to capture age: child, pre-teen, teen, old. If pictures seem to conflict, ignore this trait. If human: capture skin color. If animal: color, any color pattern, if animal has fur is it fluffy, long hair, etc.\n2) any quirky or unusual trails such as snaggle tooth, eye orientation (crossed, lazy, drifting, etc), different color of eyes, etc.\n3) hair or fur style (do the pictures show the subject to have spike or frosted tips in thier hair/fur/mane/etc)\n4) Capture detailed information about eyes, ears, hair/fur/mane/etc, body type: (slim, overweight, athletic, etc, without negative connotations).\n5) Capture anything else relevant.\n\nAlso create a list of 5 fun, personal, entertaining, age appropriate archetypes based on the visual description.\n\nReturn EXACTLY a JSON object with this schema: { \"visual_description\": \"...\", \"archetypes\": [\"The ...\", \"The ...\"] } without markdown formatting."

        # Convert base64 to parts format required by google-generativeai
        prompt_parts = [
            system_instruction,
            {"mime_type": req.mime_type, "data": req.image_base64}
        ]

        response = model.generate_content(prompt_parts)
        
        # Extract the JSON text from response
        text = response.text
        # Sometimes it returns markdown code blocks, strip them if present
        text = text.replace('```json', '').replace('```', '').strip()
        
        result_json = json.loads(text)
        return result_json
        
    except Exception as e:
        print(f"Error analyzing image: {e}")
        raise HTTPException(status_code=500, detail=str(e))

