#!/usr/bin/env python3
"""Test updating a customer's email marketing status.

This script tests updating a single customer to verify the API calls work correctly.
"""

import asyncio
import logging
import sys

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


async def test_rest_api(customer_id: int):
    """Test updating via REST API."""
    logger = logging.getLogger(__name__)
    settings = get_settings()
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Testing REST API Update for Customer {customer_id}")
    logger.info(f"{'='*60}")
    
    async with ShopifyClient(settings) as client:
        # Get current state
        logger.info("Fetching current state...")
        response = await client._request("GET", f"/customers/{customer_id}.json")
        customer = response.get("customer", {})
        current_state = customer.get("email_marketing_consent", {}).get("state")
        logger.info(f"Current state: {current_state}")
        
        # Update to subscribed
        logger.info("\nUpdating to subscribed...")
        try:
            await client.update_customer_email_marketing(customer_id, accepts_marketing=True)
            logger.info("✓ Update successful")
        except Exception as e:
            logger.error(f"✗ Update failed: {e}")
            return False
        
        # Verify
        logger.info("\nVerifying update...")
        response = await client._request("GET", f"/customers/{customer_id}.json")
        customer = response.get("customer", {})
        new_state = customer.get("email_marketing_consent", {}).get("state")
        logger.info(f"New state: {new_state}")
        
        if new_state == "subscribed":
            logger.info("✓ Verification successful - customer is now subscribed")
            return True
        else:
            logger.error(f"✗ Verification failed - expected 'subscribed', got '{new_state}'")
            return False


async def test_graphql_api(customer_id: int):
    """Test updating via GraphQL API."""
    logger = logging.getLogger(__name__)
    settings = get_settings()
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Testing GraphQL API Update for Customer {customer_id}")
    logger.info(f"{'='*60}")
    
    async with ShopifyGraphQLClient(settings) as client:
        # Get current state
        logger.info("Fetching current state...")
        query = """
        query($id: ID!) {
          customer(id: $id) {
            id
            email
            emailMarketingConsent {
              marketingState
              marketingOptInLevel
            }
          }
        }
        """
        data = await client._query(query, {"id": f"gid://shopify/Customer/{customer_id}"})
        customer = data.get("customer", {})
        current_state = customer.get("emailMarketingConsent", {}).get("marketingState")
        logger.info(f"Current state: {current_state}")
        
        # Update to subscribed
        logger.info("\nUpdating to subscribed...")
        try:
            await client.update_customer_email_marketing(customer_id, accepts_marketing=True)
            logger.info("✓ Update successful")
        except Exception as e:
            logger.error(f"✗ Update failed: {e}")
            return False
        
        # Verify
        logger.info("\nVerifying update...")
        data = await client._query(query, {"id": f"gid://shopify/Customer/{customer_id}"})
        customer = data.get("customer", {})
        new_state = customer.get("emailMarketingConsent", {}).get("marketingState")
        logger.info(f"New state: {new_state}")
        
        if new_state == "SUBSCRIBED":
            logger.info("✓ Verification successful - customer is now subscribed")
            return True
        else:
            logger.error(f"✗ Verification failed - expected 'SUBSCRIBED', got '{new_state}'")
            return False


async def main():
    """Main entry point."""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Use the customer that's currently NOT subscribed
    test_customer_id = 24582851297655
    
    logger.info("="*60)
    logger.info("TESTING EMAIL MARKETING UPDATE")
    logger.info("="*60)
    logger.info(f"\nTest customer: {test_customer_id}")
    logger.info("This customer is currently NOT subscribed")
    logger.info("We will update them to subscribed and verify")
    
    # Test REST API
    rest_success = await test_rest_api(test_customer_id)
    
    # Wait a bit between tests
    await asyncio.sleep(2)
    
    # Test GraphQL API (should already be subscribed from REST test)
    graphql_success = await test_graphql_api(test_customer_id)
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("TEST SUMMARY")
    logger.info("="*60)
    logger.info(f"REST API: {'✓ PASSED' if rest_success else '✗ FAILED'}")
    logger.info(f"GraphQL API: {'✓ PASSED' if graphql_success else '✗ FAILED'}")
    
    if rest_success and graphql_success:
        logger.info("\n✓ All tests passed! Email marketing update is working correctly.")
        return 0
    else:
        logger.error("\n✗ Some tests failed. Check the output above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
