#!/usr/bin/env python3
"""Load pricing data from YAML into MySQL llm_pricing table.

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
import aiomysql


async def load_pricing_to_mysql(
    yaml_path: str,
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
) -> None:
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    entries = data.get("pricing", [])
    if not entries:
        print("No pricing entries found in YAML file")
        return

    records = [
        (
            entry["model"],
            entry["provider"],
            entry["request_type"],
            entry["currency"].upper(),
            entry["input"],
            entry["output"],
        )
        for entry in entries
    ]

    print(f"Loading {len(records)} pricing records into llm_pricing...")

    pool = await aiomysql.create_pool(
        host=host, port=port, user=user, password=password,
        db=database, autocommit=True, charset="utf8mb4",
    )
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.executemany(
                """INSERT INTO `llm_pricing`
                   (`model`, `provider`, `request_type`, `currency_type`, `input_price`, `output_price`)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                       `currency_type` = VALUES(`currency_type`),
                       `input_price`   = VALUES(`input_price`),
                       `output_price`  = VALUES(`output_price`),
                       `updated_at`    = CURRENT_TIMESTAMP""",
                records,
            )
    pool.close()
    await pool.wait_closed()

    print(f"Successfully loaded {len(records)} pricing records")


async def main() -> None:
    import os

    host = os.environ.get("MYSQL_HOST", "localhost")
    port = int(os.environ.get("MYSQL_PORT", "3306"))
    user = os.environ.get("MYSQL_USER", "root")
    password = os.environ.get("MYSQL_PASSWORD", "")
    database = os.environ.get("MYSQL_DB", "openfriday")

    if not host or not user:
        print("Error: MYSQL_HOST and MYSQL_USER environment variables required")
        sys.exit(1)

    yaml_path = sys.argv[1] if len(sys.argv) > 1 else "llm_proxy/pricing.yaml"

    if not Path(yaml_path).exists():
        print(f"Error: pricing file not found: {yaml_path}")
        sys.exit(1)

    await load_pricing_to_mysql(yaml_path, host, port, user, password, database)


if __name__ == "__main__":
    asyncio.run(main())
