#!/usr/bin/env python3
"""Debug script to fetch a specific product and see the raw data."""

import asyncio
import json
from src.config import get_settings
from src.shopify_client import ShopifyClient


async def main():
    """Fetch and display a specific product."""
    settings = get_settings()
    
    async with ShopifyClient(settings) as client:
        # Fetch the problematic product
        product_id = 15329589330295
        
        print(f"Fetching product {product_id}...")
        
        # Make raw API call
        url = f"products/{product_id}.json"
        response = await client._request("GET", url)
        
        print("\nRaw product data:")
        print(json.dumps(response, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
