#!/usr/bin/env python3
"""Check a contact in Xero to verify IsCustomer flag."""

import asyncio
from src.config import get_settings
from src.xero_client import XeroClient


async def main():
    settings = get_settings()
    
    async with XeroClient(settings) as client:
        # Check the contact
        contact_id = "afc8ea3a-cd8f-4b5a-bf8b-91679aaedd29"
        
        contact = await client.get_contact(contact_id)
        
        if contact:
            print(f"Contact: {contact.Name}")
            print(f"Email: {contact.EmailAddress}")
            print(f"IsCustomer: {contact.IsCustomer}")
            print(f"IsSupplier: {contact.IsSupplier}")
            print(f"Status: {contact.ContactStatus}")
        else:
            print("Contact not found")


if __name__ == "__main__":
    asyncio.run(main())
