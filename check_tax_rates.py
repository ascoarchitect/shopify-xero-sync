#!/usr/bin/env python3
"""Quick script to fetch and display available tax rates from Xero."""

import asyncio
import sys
from src.config import get_settings
from src.xero_client import XeroClient


async def main():
    """Fetch and display tax rates."""
    try:
        settings = get_settings()
    except Exception as e:
        print(f"Failed to load settings: {e}")
        return 1

    async with XeroClient(settings) as xero_client:
        # Check connection
        if not await xero_client.check_connection():
            print("Failed to connect to Xero API")
            return 1

        print("Connected to Xero successfully!\n")
        
        # Fetch tax rates
        try:
            tax_rates = await xero_client.get_tax_rates()
            
            print(f"Found {len(tax_rates)} tax rates:\n")
            print(f"{'Tax Type':<25} {'Name':<40} {'Rate':<10} {'Status'}")
            print("=" * 85)
            
            for rate in tax_rates:
                tax_type = rate.get('TaxType', 'N/A')
                name = rate.get('Name', 'N/A')
                effective_rate = rate.get('EffectiveRate', 'N/A')
                status = rate.get('Status', 'N/A')
                
                print(f"{tax_type:<25} {name:<40} {effective_rate:<10} {status}")
            
            print("\n" + "=" * 85)
            print("\nUse these TaxType values in src/constants.py")
            
        except Exception as e:
            print(f"Failed to fetch tax rates: {e}")
            return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
