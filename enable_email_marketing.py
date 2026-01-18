#!/usr/bin/env python3
"""Enable email marketing for all Shopify customers.

This script updates all customers in Shopify to accept email marketing.
Useful for migrating from another platform where email consent wasn't transferred.

Usage:
    python enable_email_marketing.py [--dry-run]

Options:
    --dry-run    Show what would be updated without making changes
"""

import asyncio
import logging
import sys
from pathlib import Path

from src.config import get_settings
from src.database import Database
from src.shopify_client import ShopifyClient
from src.shopify_graphql_client import ShopifyGraphQLClient
from src.xero_client import XeroClient
from src.sync_engine import SyncEngine


def setup_logging(log_level: str = "INFO") -> None:
    """Configure logging for the script."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


async def main():
    """Main entry point."""
    # Parse arguments
    dry_run = "--dry-run" in sys.argv

    # Load settings
    settings = get_settings()
    settings.dry_run = dry_run

    # Setup logging
    setup_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("SHOPIFY EMAIL MARKETING ENABLER")
    logger.info("=" * 60)

    if dry_run:
        logger.info("Running in DRY RUN mode - no changes will be made")
    else:
        logger.warning("This will update ALL customers in Shopify to accept email marketing")
        response = input("Are you sure you want to continue? (yes/no): ")
        if response.lower() != "yes":
            logger.info("Operation cancelled")
            return

    # Initialize database
    db = Database(settings.database_path)

    # Choose Shopify client based on configuration
    if settings.shopify_api_type == "graphql":
        logger.info("Using Shopify GraphQL API")
        shopify_client = ShopifyGraphQLClient(settings)
    else:
        logger.info("Using Shopify REST API")
        shopify_client = ShopifyClient(settings)

    # Initialize Xero client (needed for sync engine, but won't be used)
    xero_client = XeroClient(settings)

    try:
        # Initialize clients
        async with shopify_client, xero_client:
            # Verify Shopify connection
            logger.info("Verifying Shopify connection...")
            if not await shopify_client.check_connection():
                logger.error("Failed to connect to Shopify API")
                return 1

            # Create sync engine
            sync_engine = SyncEngine(
                settings=settings,
                database=db,
                shopify_client=shopify_client,
                xero_client=xero_client,
                dry_run=dry_run,
            )

            # Run email marketing update
            result = await sync_engine.enable_email_marketing_for_all_customers()

            # Print summary
            logger.info("")
            logger.info("=" * 60)
            logger.info("SUMMARY")
            logger.info("=" * 60)
            logger.info(f"Customers updated: {result.updated}")
            logger.info(f"Errors: {len(result.errors)}")

            if result.errors:
                logger.info("")
                logger.info("Errors encountered:")
                for error in result.errors[:10]:  # Show first 10 errors
                    logger.error(f"  - {error}")
                if len(result.errors) > 10:
                    logger.info(f"  ... and {len(result.errors) - 10} more errors")

            logger.info("=" * 60)

            return 0 if result.success else 1

    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
