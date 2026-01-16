#!/usr/bin/env python3
"""Test updating a contact with IsCustomer flag."""

import asyncio
from src.config import get_settings
from src.xero_client import XeroClient
from src.models import XeroContact


async def main():
    settings = get_settings()
    
    async with XeroClient(settings) as client:
        # Get the contact
        contact_id = "fdd7d74f-7478-4af6-af20-b3b1f5059633"
        
        print("Fetching contact...")
        contact = await client.get_contact(contact_id)
        
        if not contact:
            print("Contact not found")
            return
        
        print(f"Before update:")
        print(f"  Name: {contact.Name}")
        print(f"  IsCustomer: {contact.IsCustomer}")
        print(f"  IsSupplier: {contact.IsSupplier}")
        
        # Update with IsCustomer=True
        contact.IsCustomer = True
        contact.IsSupplier = False
        
        print(f"\nUpdating contact with IsCustomer=True...")
        updated = await client.update_contact(contact)
        
        print(f"\nAfter update (from API response):")
        print(f"  Name: {updated.Name}")
        print(f"  IsCustomer: {updated.IsCustomer}")
        print(f"  IsSupplier: {updated.IsSupplier}")
        
        # Fetch again to verify
        print(f"\nFetching again to verify...")
        verified = await client.get_contact(contact_id)
        print(f"  IsCustomer: {verified.IsCustomer}")
        print(f"  IsSupplier: {verified.IsSupplier}")


if __name__ == "__main__":
    asyncio.run(main())
