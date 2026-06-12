import asyncio
import os
import logging
from src.lib.mcp_integration import _call_mcp_tool

logging.basicConfig(level=logging.INFO)

async def main():
    queries = [
        "United States inflation rate",
        "Population of Thailand"
    ]
    for q in queries:
        print(f"\n--- Query: {q} ---")
        try:
            args = {
                "query": q,
                "api_token": os.getenv("TAKO_API_KEY", ""),
                "count": 5,
                "search_effort": "fast",
                "country_code": "US",
                "locale": "en-US"
            }
            result = await _call_mcp_tool("knowledge_search", args)
            print("RAW RESULT:")
            import json
            print(json.dumps(result, indent=2))
        except Exception as e:
            print(f"Exception: {e}")

asyncio.run(main())
