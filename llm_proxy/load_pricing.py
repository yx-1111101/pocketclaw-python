#!/usr/bin/env python3
"""Load pricing data from YAML into Supabase llm_pricing table.

YAML format (pricing.yaml):
  pricing:
    - model:        gpt-4o
      provider:     zhizengzeng
      request_type: openai
      currency:     USD
      input:        2.50        # per 1M input tokens
      output:       10.00       # per 1M output tokens
"""
import asyncio
import sys
from pathlib import Path
import yaml
import httpx


async def load_pricing_to_supabase(
    yaml_path: str,
    supabase_url: str,
    supabase_key: str,
) -> None:
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    entries = data.get("pricing", [])
    if not entries:
        print("No pricing entries found in YAML file")
        return

    records = [
        {
            "model":        entry["model"],
            "provider":     entry["provider"],
            "request_type": entry["request_type"],
            "currency_type": entry["currency"].upper(),
            "input_price":  entry["input"],
            "output_price": entry["output"],
        }
        for entry in entries
    ]

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    print(f"Loading {len(records)} pricing records into llm_pricing...")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{supabase_url.rstrip('/')}/rest/v1/llm_pricing",
            headers=headers,
            json=records,
        )
        if resp.status_code >= 400:
            print(f"Error {resp.status_code}: {resp.text}")
            sys.exit(1)

    print(f"Successfully loaded {len(records)} pricing records")


async def main() -> None:
    import os

    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_KEY", "")

    if not supabase_url or not supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_KEY environment variables required")
        sys.exit(1)

    yaml_path = sys.argv[1] if len(sys.argv) > 1 else "pricing.yaml"

    if not Path(yaml_path).exists():
        print(f"Error: pricing file not found: {yaml_path}")
        sys.exit(1)

    await load_pricing_to_supabase(yaml_path, supabase_url, supabase_key)


if __name__ == "__main__":
    asyncio.run(main())
