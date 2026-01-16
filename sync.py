#!/usr/bin/env python3
"""Main entry point for Shopify-Xero sync.

Usage:
    python sync.py              # Run full sync
    python sync.py --dry-run    # Run without making changes
    python sync.py --retry      # Retry failed syncs only
    python sync.py --stats      # Show sync statistics
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from pythonjsonlogger import jsonlogger

from src.config import get_settings, Settings
from src.database import Database
from src.shopify_client import ShopifyClient
from src.shopify_graphql_client import ShopifyGraphQLClient
from src.xero_client import XeroClient
from src.sync_engine import SyncEngine


def setup_logging(settings: Settings) -> None:
    """Configure logging for the application.

    Args:
        settings: Application settings
    """
    # Ensure log directory exists
    settings.log_file.parent.mkdir(parents=True, exist_ok=True)

    # Create formatters
    console_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    json_formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.DEBUG)

    # File handler (JSON format for parsing)
    file_handler = logging.FileHandler(settings.log_file)
    file_handler.setFormatter(json_formatter)
    file_handler.setLevel(logging.DEBUG)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level))
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Reduce noise from httpx
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def run_sync(args: argparse.Namespace) -> int:
    """Run the sync operation.

    Args:
        args: Command line arguments

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    logger = logging.getLogger(__name__)

    try:
        settings = get_settings()
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        logger.error("Make sure .env file exists with required environment variables")
        return 1

    setup_logging(settings)

    logger.info("=" * 60)
    logger.info("Shopify-Xero Sync Starting")
    logger.info("=" * 60)

    if args.dry_run:
        logger.info("DRY RUN MODE ENABLED - No changes will be made")
        settings.dry_run = True

    # Initialize database
    database = Database(settings.database_path)

    # Handle stats command
    if args.stats:
        stats = database.get_stats()
        logger.info("Sync Statistics:")
        logger.info(f"  Mappings by type: {stats.get('mappings', {})}")
        logger.info(f"  Pending errors: {stats.get('pending_errors', 0)}")
        logger.info(f"  Last successful sync: {stats.get('last_successful_sync', 'Never')}")
        return 0

    # Run sync with API clients
    # Choose between REST and GraphQL based on configuration
    if settings.shopify_api_type == "graphql":
        logger.info("Using Shopify GraphQL API (faster bulk operations)")
        shopify_client_class = ShopifyGraphQLClient
    else:
        logger.info("Using Shopify REST API")
        shopify_client_class = ShopifyClient
    
    async with shopify_client_class(settings) as shopify_client:
        async with XeroClient(settings) as xero_client:
            engine = SyncEngine(
                settings=settings,
                database=database,
                shopify_client=shopify_client,
                xero_client=xero_client,
                dry_run=args.dry_run,
            )

            # Verify connections
            logger.info("Verifying API connections...")
            shopify_ok, xero_ok = await engine.verify_connections()

            if not shopify_ok:
                logger.error("Cannot connect to Shopify API")
                return 1

            if not xero_ok:
                logger.error("Cannot connect to Xero API")
                logger.error("You may need to re-authorize the app or refresh tokens")
                return 1

            logger.info("API connections verified successfully")

            # Run appropriate sync operation
            if args.retry:
                logger.info("Running retry of failed syncs...")
                result = await engine.retry_failed_syncs()
            else:
                if args.force:
                    logger.info("Running FORCED full sync (ignoring last sync timestamp)...")
                else:
                    logger.info("Running full sync...")
                stats = await engine.run_full_sync(force=args.force)
                result = stats.customers

            # Report results
            if result:
                logger.info("=" * 60)
                logger.info("Sync Complete")
                logger.info("=" * 60)
                logger.info(f"  Created: {result.created}")
                logger.info(f"  Updated: {result.updated}")
                logger.info(f"  Skipped: {result.skipped}")
                logger.info(f"  Errors: {len(result.errors)}")

                if result.errors:
                    logger.warning("Errors encountered:")
                    for error in result.errors[:10]:  # Show first 10 errors
                        logger.warning(f"  - {error}")
                    if len(result.errors) > 10:
                        logger.warning(f"  ... and {len(result.errors) - 10} more")
                    return 1

            return 0

    return 0


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Sync customers, products, and orders from Shopify to Xero",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python sync.py              Run a full sync
  python sync.py --dry-run    Run without making changes to Xero
  python sync.py --force      Force sync all entities (ignore last sync time)
  python sync.py --retry      Retry previously failed sync operations
  python sync.py --stats      Show sync statistics
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually make changes to Xero, just log what would happen",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force a full sync of all entities, ignoring last sync timestamp",
    )

    parser.add_argument(
        "--retry",
        action="store_true",
        help="Retry previously failed sync operations only",
    )

    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show sync statistics and exit",
    )

    args = parser.parse_args()

    # Run async main
    exit_code = asyncio.run(run_sync(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
