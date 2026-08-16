#!/usr/bin/env python3
"""
Antigravity MCP Server for Local MLX Models (oMLX)
===================================================
Provides tool integration allowing Antigravity agents to query local Apple Silicon
MLX models (e.g., Qwen 2.5 72B, Llama 3.3 70B) hosted via oMLX on port 8080.
"""

import os
import httpx
from mcp.server.mcpserver import MCPServer

server = MCPServer(name="local-mlx-models")

OMLX_BASE_URL = os.getenv("OMLX_BASE_URL", "http://127.0.0.1:8080/v1")


@server.tool()
async def list_local_models() -> str:
    """List all available local MLX models served by oMLX.

    Returns a list of model IDs currently loaded or available on the local machine.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(f"{OMLX_BASE_URL}/models")
            if res.status_code == 200:
                data = res.json()
                models = [m.get("id") for m in data.get("data", [])]
                if models:
                    return f"Available local MLX models:\n" + "\n".join(f"- {m}" for m in models)
                return "oMLX server is online, but no models are currently discovered."
            return f"Error from oMLX server (HTTP {res.status_code}): {res.text}"
    except httpx.ConnectError:
        return (
            "oMLX server is not currently running on port 8080.\n"
            "To start it, run:\n"
            "/Users/prismforge/.omlx/bin/omlx serve --port 8080 --model-dir /Users/prismforge/.omlx/models"
        )
    except Exception as e:
        return f"Error querying local models: {str(e)}"


@server.tool()
async def query_local_model(
    prompt: str,
    model: str = "Qwen2.5-72B-Instruct-8bit",
    system_prompt: str = "You are a helpful, knowledgeable, and precise AI assistant running locally on Apple Silicon.",
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> str:
    """Query a local Apple Silicon MLX model (Qwen 2.5 72B or Llama 3.3 70B) via oMLX.

    Args:
        prompt: The user prompt or instructions for the local model.
        model: Identifier of the local model to query (e.g. 'Qwen2.5-72B-Instruct-8bit' or 'Llama-3.3-70B-Instruct-8bit').
        system_prompt: Optional system instruction directing the model's persona or formatting.
        temperature: Sampling temperature between 0.0 and 1.0 (default: 0.7).
        max_tokens: Maximum number of tokens to generate (default: 2048).
    """
    # Clean up model name if passed with 'mlx-community/' prefix
    target_model = model.replace("mlx-community/", "")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": target_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            res = await client.post(f"{OMLX_BASE_URL}/chat/completions", json=payload)
            if res.status_code == 200:
                data = res.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
                return "Model returned an empty response."
            return f"Error from oMLX server (HTTP {res.status_code}): {res.text}"
    except httpx.ConnectError:
        return (
            "oMLX server is not currently running on port 8080.\n"
            "To start it, run:\n"
            "/Users/prismforge/.omlx/bin/omlx serve --port 8080 --model-dir /Users/prismforge/.omlx/models"
        )
    except Exception as e:
        return f"Error during local model inference: {str(e)}"


if __name__ == "__main__":
    server.run("stdio")
