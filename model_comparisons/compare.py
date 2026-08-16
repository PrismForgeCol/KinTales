#!/usr/bin/env python3
"""
Local Model Comparison Script (oMLX)
=====================================
Runs a given prompt against multiple local MLX models, measures inference time,
and outputs a clean Markdown comparison file.

Usage:
  python compare.py "Your prompt here" --title "feature_test"
"""

import os
import sys
import time
import argparse
import asyncio
import httpx

OMLX_URL = os.getenv("OMLX_URL", "http://127.0.0.1:8080/v1")
DEFAULT_MODELS = [
    "Qwen2.5-72B-Instruct-8bit",
    "Llama-3.3-70B-Instruct-8bit",
]


async def query_model(client: httpx.AsyncClient, model: str, prompt: str, system_prompt: str, temperature: float, max_tokens: int):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    start = time.time()
    try:
        res = await client.post(f"{OMLX_URL}/chat/completions", json=payload, timeout=240.0)
        elapsed = time.time() - start
        if res.status_code == 200:
            data = res.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})
            return {
                "model": model,
                "success": True,
                "content": content,
                "elapsed": elapsed,
                "usage": usage
            }
        return {"model": model, "success": False, "error": f"HTTP {res.status_code}: {res.text}", "elapsed": elapsed}
    except Exception as e:
        return {"model": model, "success": False, "error": str(e), "elapsed": time.time() - start}


async def main():
    parser = argparse.ArgumentParser(description="Compare local MLX models")
    parser.add_argument("prompt", help="Prompt to evaluate")
    parser.add_argument("--system", default="You are a helpful, creative, and precise assistant.", help="System prompt")
    parser.add_argument("--title", default="comparison", help="Output filename slug")
    parser.add_argument("--temp", type=float, default=0.7, help="Temperature")
    parser.add_argument("--tokens", type=int, default=1500, help="Max tokens")
    args = parser.parse_args()

    print(f"🔬 Comparing models on prompt: \"{args.prompt[:60]}...\"")
    
    results = []
    async with httpx.AsyncClient() as client:
        for model in DEFAULT_MODELS:
            print(f"⏳ Running on {model}...")
            res = await query_model(client, model, args.prompt, args.system, args.temp, args.tokens)
            results.append(res)
            print(f"✅ Finished {model} in {res['elapsed']:.2f}s")

    # Generate Markdown Report
    output_dir = os.path.dirname(os.path.abspath(__file__))
    safe_title = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in args.title)
    output_path = os.path.join(output_dir, f"{safe_title}.md")

    md_lines = [
        f"# Model Comparison: {args.title.replace('_', ' ').title()}",
        f"",
        f"- **Prompt**: *\"{args.prompt}\"*",
        f"- **System Prompt**: *\"{args.system}\"*",
        f"- **Temperature**: `{args.temp}` | **Max Tokens**: `{args.tokens}`",
        f"",
        "---",
        ""
    ]

    for r in results:
        md_lines.append(f"## {r['model']}")
        if r['success']:
            tokens_sec = ""
            usage = r.get("usage", {})
            out_toks = usage.get("completion_tokens", usage.get("output_tokens", 0))
            if out_toks and r['elapsed'] > 0:
                tokens_sec = f" (~{out_toks / r['elapsed']:.1f} tokens/sec)"
            md_lines.append(f"*(Generated in {r['elapsed']:.2f}s{tokens_sec})*")
            md_lines.append("")
            md_lines.append(r['content'])
        else:
            md_lines.append(f"**Error**: {r.get('error')}")
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"🎉 Saved comparison to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
