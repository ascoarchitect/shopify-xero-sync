#!/usr/bin/env python3
"""Check customer email marketing status in Shopify.

This script fetches specific customers and shows their email marketing
consent details to verify we're updating the correct fields.
"""

import asyncio
import logging
import sys
import json

from src.config import get_settings
from src.shopify_client import ShopifyClient
from src.shopify_graphql_client import ShopifyGraphQLClient


def setup_logging():
    """Configure logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


async def check_customer_rest(client: ShopifyClient, customer_id: int):
    """Check customer using REST API."""
    logger = logging.getLogger(__name__)
    
    try:
        response = await client._request("GET", f"/customers/{customer_id}.json")
        customer = response.get("customer", {})
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Customer {customer_id} (REST API)")
        logger.info(f"{'='*60}")
        logger.info(f"Email: {customer.get('email')}")
        logger.info(f"Name: {customer.get('first_name')} {customer.get('last_name')}")
        logger.info(f"\nEmail Marketing Fields:")
        logger.info(f"  accepts_marketing: {customer.get('accepts_marketing')}")
        logger.info(f"  accepts_marketing_updated_at: {customer.get('accepts_marketing_updated_at')}")
        logger.info(f"  marketing_opt_in_level: {customer.get('marketing_opt_in_level')}")
        
        # Show email marketing consent object if it exists
        if 'email_marketing_consent' in customer:
            logger.info(f"\n  email_marketing_consent:")
            consent = customer['email_marketing_consent']
            for key, value in consent.items():
                logger.info(f"    {key}: {value}")
        
        logger.info(f"\nFull customer data (relevant fields):")
        relevant_fields = {
            'id': customer.get('id'),
            'email': customer.get('email'),
            'accepts_marketing': customer.get('accepts_marketing'),
            'accepts_marketing_updated_at': customer.get('accepts_marketing_updated_at'),
            'marketing_opt_in_level': customer.get('marketing_opt_in_level'),
            'email_marketing_consent': customer.get('email_marketing_consent'),
        }
        logger.info(json.dumps(relevant_fields, indent=2))
        
    except Exception as e:
        logger.error(f"Error fetching customer {customer_id}: {e}")


async def check_customer_graphql(client: ShopifyGraphQLClient, customer_id: int):
    """Check customer using GraphQL API."""
    logger = logging.getLogger(__name__)
    
    query = """
    query($id: ID!) {
      customer(id: $id) {
        id
        email
        firstName
        lastName
        emailMarketingConsent {
          marketingState
          marketingOptInLevel
          consentUpdatedAt
        }
        smsMarketingConsent {
          marketingState
          marketingOptInLevel
          consentUpdatedAt
        }
      }
    }
    """
    
    variables = {
        "id": f"gid://shopify/Customer/{customer_id}"
    }
    
    try:
        data = await client._query(query, variables)
        customer = data.get("customer", {})
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Customer {customer_id} (GraphQL API)")
        logger.info(f"{'='*60}")
        logger.info(f"Email: {customer.get('email')}")
        logger.info(f"Name: {customer.get('firstName')} {customer.get('lastName')}")
        logger.info(f"\nEmail Marketing Fields:")
        
        if customer.get('emailMarketingConsent'):
            logger.info(f"\n  emailMarketingConsent:")
            consent = customer['emailMarketingConsent']
            for key, value in consent.items():
                logger.info(f"    {key}: {value}")
        
        if customer.get('smsMarketingConsent'):
            logger.info(f"\n  smsMarketingConsent:")
            consent = customer['smsMarketingConsent']
            for key, value in consent.items():
                logger.info(f"    {key}: {value}")
        
        logger.info(f"\nFull customer data:")
        logger.info(json.dumps(customer, indent=2, default=str))
        
    except Exception as e:
        logger.error(f"Error fetching customer {customer_id}: {e}")


async def main():
    """Main entry point."""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Customer IDs to check
    customer_ids = [
        24582825542007,  # Has email marketing enabled
        24582851297655,  # Doesn't have email marketing enabled
    ]
    
    settings = get_settings()
    
    logger.info("="*60)
    logger.info("CHECKING CUSTOMER EMAIL MARKETING STATUS")
    logger.info("="*60)
    
    # Check with REST API
    logger.info("\n\nUsing REST API:")
    logger.info("-"*60)
    async with ShopifyClient(settings) as rest_client:
        for customer_id in customer_ids:
            await check_customer_rest(rest_client, customer_id)
    
    # Check with GraphQL API
    logger.info("\n\nUsing GraphQL API:")
    logger.info("-"*60)
    async with ShopifyGraphQLClient(settings) as graphql_client:
        for customer_id in customer_ids:
            await check_customer_graphql(graphql_client, customer_id)
    
    logger.info("\n" + "="*60)
    logger.info("ANALYSIS COMPLETE")
    logger.info("="*60)
    logger.info("\nCompare the fields above to determine:")
    logger.info("1. Which field indicates email marketing consent")
    logger.info("2. What values mean 'subscribed' vs 'unsubscribed'")
    logger.info("3. Whether our update mutation is targeting the right field")


if __name__ == "__main__":
    asyncio.run(main())
