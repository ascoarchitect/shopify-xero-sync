#!/usr/bin/env python3
"""Test batch operations for email marketing updates.

This script tests updating a small batch of customers to verify
the batch operations work correctly before running on all 1500+ customers.
"""

import asyncio
import logging
import sys

from src.config import get_settings
from src.shopify_graphql_client import ShopifyGraphQLClient
from src.shopify_bulk_operations import ShopifyBulkOperations


def setup_logging():
    """Configure logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


async def main():
    """Main entry point."""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    settings = get_settings()
    
    logger.info("="*60)
    logger.info("TESTING BATCH EMAIL MARKETING UPDATES")
    logger.info("="*60)
    
    # Test with a small batch of customers
    # Using customers we know exist from previous tests
    test_customer_ids = [
        24582825542007,  # Carla (already subscribed)
        24582851297655,  # Caroline (we updated earlier)
    ]
    
    logger.info(f"\nTesting with {len(test_customer_ids)} customers")
    
    async with ShopifyGraphQLClient(settings) as client:
        # Verify connection
        logger.info("Verifying Shopify connection...")
        if not await client.check_connection():
            logger.error("Failed to connect to Shopify")
            return 1
        
        # Create bulk operations handler
        bulk_ops = ShopifyBulkOperations(client)
        
        # Test batch update
        logger.info("\nStarting batch update...")
        result = await bulk_ops.batch_update_customer_email_marketing(
            customer_ids=test_customer_ids,
            accepts_marketing=True,
            batch_size=10  # Small batch for testing
        )
        
        # Display results
        logger.info("\n" + "="*60)
        logger.info("BATCH UPDATE RESULTS")
        logger.info("="*60)
        logger.info(f"Total customers: {result['total']}")
        logger.info(f"Successfully updated: {result['updated']}")
        logger.info(f"Failed: {result['failed']}")
        logger.info(f"Duration: {result['duration']:.2f}s")
        logger.info(f"Average time per customer: {result['duration']/result['total']:.3f}s")
        
        if result['errors']:
            logger.info(f"\nErrors ({len(result['errors'])}):")
            for error in result['errors'][:5]:
                logger.error(f"  - {error}")
            if len(result['errors']) > 5:
                logger.info(f"  ... and {len(result['errors'] - 5)} more")
        
        # Verify updates
        logger.info("\n" + "="*60)
        logger.info("VERIFYING UPDATES")
        logger.info("="*60)
        
        for customer_id in test_customer_ids:
            query = """
            query($id: ID!) {
              customer(id: $id) {
                id
                email
                emailMarketingConsent {
                  marketingState
                  consentUpdatedAt
                }
              }
            }
            """
            data = await client._query(query, {"id": f"gid://shopify/Customer/{customer_id}"})
            customer = data.get("customer", {})
            consent = customer.get("emailMarketingConsent", {})
            
            logger.info(
                f"Customer {customer_id} ({customer.get('email')}): "
                f"{consent.get('marketingState')} "
                f"(updated: {consent.get('consentUpdatedAt')})"
            )
        
        logger.info("\n" + "="*60)
        if result['success']:
            logger.info("✓ Batch operations test PASSED")
            logger.info("\nYou can now run the full update with confidence:")
            logger.info("  python enable_email_marketing.py")
            return 0
        else:
            logger.error("✗ Batch operations test FAILED")
            logger.error("Check the errors above before running on all customers")
            return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
