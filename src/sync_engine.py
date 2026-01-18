"""Core sync orchestration engine.

Manages the synchronization flow between Shopify and Xero,
handling change detection, duplicate prevention, and error recovery.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass, field

from .config import Settings
from .database import Database
from .shopify_client import ShopifyClient, ShopifyAPIError
from .xero_client import XeroClient, XeroAPIError
from .models import (
    ShopifyCustomer,
    ShopifyProduct,
    ShopifyOrder,
    XeroContact,
    XeroItem,
    XeroInvoice,
    SyncMapping,
    shopify_customer_to_xero_contact,
    shopify_product_to_xero_item,
    shopify_order_to_xero_invoice,
)
from .checksums import (
    calculate_customer_checksum,
    calculate_product_checksum,
    calculate_order_checksum,
    has_changed,
)

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of a sync operation."""
    success: bool
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def total_processed(self) -> int:
        return self.created + self.updated + self.skipped


@dataclass
class SyncStats:
    """Statistics for a complete sync run."""
    run_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    customers: Optional[SyncResult] = None
    products: Optional[SyncResult] = None
    orders: Optional[SyncResult] = None

    @property
    def total_errors(self) -> List[str]:
        errors = []
        if self.customers:
            errors.extend(self.customers.errors)
        if self.products:
            errors.extend(self.products.errors)
        if self.orders:
            errors.extend(self.orders.errors)
        return errors

    @property
    def total_processed(self) -> int:
        total = 0
        if self.customers:
            total += self.customers.total_processed
        if self.products:
            total += self.products.total_processed
        if self.orders:
            total += self.orders.total_processed
        return total

    @property
    def success(self) -> bool:
        return len(self.total_errors) == 0


class SyncEngine:
    """Orchestrates sync between Shopify and Xero."""

    def __init__(
        self,
        settings: Settings,
        database: Database,
        shopify_client: ShopifyClient,
        xero_client: XeroClient,
        dry_run: bool = False,
    ):
        """Initialize sync engine.

        Args:
            settings: Application settings
            database: Database instance for state tracking
            shopify_client: Shopify API client (REST or GraphQL)
            xero_client: Xero API client
            dry_run: If True, don't actually make changes to Xero
        """
        self.settings = settings
        self.db = database
        self.shopify = shopify_client
        self.xero = xero_client
        self.dry_run = dry_run or settings.dry_run

    async def _fetch_entities(self, fetch_method, *args, **kwargs):
        """Helper to handle both REST (async generator) and GraphQL (list) responses.
        
        Args:
            fetch_method: The fetch method to call
            *args, **kwargs: Arguments to pass to the fetch method
            
        Returns:
            List of entities
        """
        result = fetch_method(*args, **kwargs)
        
        # Check if it's an async generator (REST) or awaitable (GraphQL)
        if hasattr(result, '__aiter__'):
            # REST API - async generator, collect into list
            entities = []
            async for entity in result:
                entities.append(entity)
            return entities
        else:
            # GraphQL API - returns awaitable list
            return await result

    async def run_full_sync(self, force: bool = False) -> SyncStats:
        """Run a complete sync of all entity types.

        Sync order: Customers -> Products -> Orders
        (Orders depend on having customers and products synced first)

        Args:
            force: If True, ignore last sync timestamp and sync all entities

        Returns:
            SyncStats with results of the sync run
        """
        run_id = str(uuid.uuid4())
        started_at = datetime.utcnow()

        logger.info(f"Starting full sync run: {run_id}")
        if self.dry_run:
            logger.info("DRY RUN MODE - No changes will be made to Xero")
        if force:
            logger.info("FORCE MODE - Syncing all entities regardless of last sync time")

        self.db.start_sync_run(run_id)

        stats = SyncStats(run_id=run_id, started_at=started_at)

        try:
            # Sync customers first (orders need customer contacts)
            logger.info("=" * 50)
            logger.info("PHASE 1: Syncing customers...")
            logger.info("=" * 50)
            stats.customers = await self.sync_customers(force=force)

            # Sync products (orders can link to product items)
            logger.info("=" * 50)
            logger.info("PHASE 2: Syncing products...")
            logger.info("=" * 50)
            stats.products = await self.sync_products(force=force)

            # Sync orders (depends on customers and products)
            logger.info("=" * 50)
            logger.info("PHASE 3: Syncing orders...")
            logger.info("=" * 50)
            stats.orders = await self.sync_orders(force=force)

            stats.completed_at = datetime.utcnow()

            # Record completion
            status = "success" if stats.success else "failed"
            self.db.complete_sync_run(
                run_id=run_id,
                status=status,
                entities_processed=stats.total_processed,
                errors=stats.total_errors,
            )

            duration = (stats.completed_at - started_at).total_seconds()
            logger.info("=" * 50)
            logger.info(f"SYNC COMPLETE: {run_id}")
            logger.info(f"Duration: {duration:.1f}s")
            logger.info(f"Status: {status}")
            logger.info(f"Total processed: {stats.total_processed}")
            logger.info(f"Total errors: {len(stats.total_errors)}")
            logger.info("=" * 50)

        except Exception as e:
            logger.error(f"Sync run {run_id} failed with exception: {e}")
            self.db.complete_sync_run(
                run_id=run_id,
                status="failed",
                entities_processed=0,
                errors=[str(e)],
            )
            raise

        return stats

    # =========================================================================
    # CUSTOMER SYNC
    # =========================================================================

    async def sync_customers(self, force: bool = False) -> SyncResult:
        """Sync all customers from Shopify to Xero.

        Args:
            force: If True, sync all customers regardless of last sync time

        Returns:
            SyncResult with counts of created/updated/skipped/errors
        """
        result = SyncResult(success=True)

        try:
            # Get last successful sync time for incremental sync
            last_sync = self.db.get_last_successful_sync()
            updated_at_min = None if force else (last_sync.completed_at if last_sync else None)

            logger.info(
                f"Fetching customers from Shopify "
                f"(updated since: {updated_at_min or 'all time'})"
            )

            # Fetch customers (handles both REST and GraphQL)
            customers = await self._fetch_entities(
                self.shopify.fetch_all_customers,
                updated_at_min=updated_at_min
            )
            
            for customer in customers:
                try:
                    action, error = await self._sync_single_customer(customer)
                    if error:
                        result.errors.append(error)
                        self.db.record_error("customer", str(customer.id), error)
                    elif action == "created":
                        result.created += 1
                    elif action == "updated":
                        result.updated += 1
                    elif action == "skipped":
                        result.skipped += 1

                except Exception as e:
                    error_msg = f"Customer {customer.id}: {str(e)}"
                    logger.error(error_msg)
                    result.errors.append(error_msg)
                    self.db.record_error("customer", str(customer.id), str(e))

        except Exception as e:
            logger.error(f"Failed to fetch customers: {e}")
            result.errors.append(f"Fetch failed: {str(e)}")
            result.success = False

        logger.info(
            f"Customer sync complete: "
            f"{result.created} created, {result.updated} updated, "
            f"{result.skipped} skipped, {len(result.errors)} errors"
        )

        return result

    async def _sync_single_customer(
        self,
        customer: ShopifyCustomer,
    ) -> Tuple[str, Optional[str]]:
        """Sync a single customer to Xero."""
        shopify_id = str(customer.id)
        new_checksum = calculate_customer_checksum(customer)

        # Update email marketing consent if enabled
        if self.settings.enable_email_marketing:
            try:
                await self._update_customer_email_marketing(customer.id)
            except Exception as e:
                logger.warning(f"Failed to update email marketing for customer {shopify_id}: {e}")
                # Don't fail the sync if email marketing update fails

        # Check existing mapping
        mapping = self.db.get_mapping(shopify_id)

        if mapping:
            # Entity exists in our database - check if changed
            if not has_changed(mapping.checksum, new_checksum):
                logger.debug(f"Customer {shopify_id} unchanged, skipping")
                return ("skipped", None)

            # Changed - update in Xero
            return await self._update_customer_in_xero(
                customer, mapping, new_checksum
            )
        else:
            # New entity - check for duplicates in Xero first
            return await self._create_customer_in_xero(customer, new_checksum)

    async def _create_customer_in_xero(
        self,
        customer: ShopifyCustomer,
        checksum: str,
    ) -> Tuple[str, Optional[str]]:
        """Create a new customer in Xero (with duplicate checking)."""
        shopify_id = str(customer.id)

        # Check for existing contact in Xero by email (duplicate prevention)
        existing_contact = None
        if customer.email:
            try:
                existing_contact = await self.xero.find_contact_by_email(customer.email)
            except XeroAPIError as e:
                logger.warning(f"Failed to search for existing contact: {e}")

        if existing_contact:
            # Check if the contact is archived
            if existing_contact.ContactStatus == "ARCHIVED":
                logger.info(
                    f"Found ARCHIVED Xero contact for {customer.email}, "
                    f"will create new contact instead"
                )
                # Don't link to archived contact, create a new one
                existing_contact = None
            else:
                # Found existing active Xero contact - link it and update if needed
                logger.info(
                    f"Found existing Xero contact for {customer.email}: "
                    f"{existing_contact.ContactID}"
                )
                
                # Create mapping
                mapping = SyncMapping(
                    shopify_id=shopify_id,
                    xero_id=existing_contact.ContactID,
                    entity_type="customer",
                    last_synced_at=datetime.utcnow(),
                    shopify_updated_at=customer.updated_at,
                    checksum=checksum,
                )
                self.db.upsert_mapping(mapping)
                self.db.clear_error(shopify_id)
                
                # Now update the existing contact with current Shopify data
                # This ensures Xero has the latest information
                xero_contact = shopify_customer_to_xero_contact(customer)
                xero_contact.ContactID = existing_contact.ContactID
                
                if self.dry_run:
                    logger.info(f"[DRY RUN] Would update existing contact: {xero_contact.Name}")
                    return ("updated", None)
                
                try:
                    await self.xero.update_contact(xero_contact)
                    logger.info(f"Updated existing Xero contact for customer {shopify_id}")
                    return ("updated", None)
                except XeroAPIError as e:
                    error_msg = f"Failed to update existing contact for customer {shopify_id}: {e}"
                    logger.error(error_msg)
                    return ("skipped", error_msg)

        # No existing active contact found - create new one        # Convert to Xero contact
        xero_contact = shopify_customer_to_xero_contact(customer)

        if self.dry_run:
            logger.info(f"[DRY RUN] Would create contact: {xero_contact.Name}")
            return ("created", None)

        try:
            created_contact = await self.xero.create_contact(xero_contact)

            # Save mapping
            mapping = SyncMapping(
                shopify_id=shopify_id,
                xero_id=created_contact.ContactID,
                entity_type="customer",
                last_synced_at=datetime.utcnow(),
                shopify_updated_at=customer.updated_at,
                checksum=checksum,
            )
            self.db.upsert_mapping(mapping)
            self.db.clear_error(shopify_id)

            logger.info(f"Created Xero contact for customer {shopify_id}")
            return ("created", None)

        except XeroAPIError as e:
            error_msg = f"Failed to create contact for customer {shopify_id}: {e}"
            logger.error(error_msg)
            return ("skipped", error_msg)

    async def _update_customer_in_xero(
        self,
        customer: ShopifyCustomer,
        mapping: SyncMapping,
        new_checksum: str,
    ) -> Tuple[str, Optional[str]]:
        """Update an existing customer in Xero."""
        shopify_id = str(customer.id)

        # Convert to Xero contact with existing ID
        xero_contact = shopify_customer_to_xero_contact(customer)
        xero_contact.ContactID = mapping.xero_id

        if self.dry_run:
            logger.info(f"[DRY RUN] Would update contact: {xero_contact.Name}")
            return ("updated", None)

        try:
            await self.xero.update_contact(xero_contact)

            # Update mapping
            mapping.last_synced_at = datetime.utcnow()
            mapping.shopify_updated_at = customer.updated_at
            mapping.checksum = new_checksum
            self.db.upsert_mapping(mapping)
            self.db.clear_error(shopify_id)

            logger.info(f"Updated Xero contact for customer {shopify_id}")
            return ("updated", None)

        except XeroAPIError as e:
            error_msg = f"Failed to update contact for customer {shopify_id}: {e}"
            logger.error(error_msg)
            return ("skipped", error_msg)

    # =========================================================================
    # PRODUCT SYNC
    # =========================================================================

    async def sync_products(self, force: bool = False) -> SyncResult:
        """Sync all products from Shopify to Xero.

        Args:
            force: If True, sync all products regardless of last sync time

        Returns:
            SyncResult with counts of created/updated/skipped/errors
        """
        result = SyncResult(success=True)

        try:
            last_sync = self.db.get_last_successful_sync()
            updated_at_min = None if force else (last_sync.completed_at if last_sync else None)

            logger.info(
                f"Fetching products from Shopify "
                f"(updated since: {updated_at_min or 'all time'})"
            )

            # Fetch products (handles both REST and GraphQL)
            products = await self._fetch_entities(
                self.shopify.fetch_all_products,
                updated_at_min=updated_at_min
            )
            
            for product in products:
                try:
                    action, error = await self._sync_single_product(product)
                    if error:
                        result.errors.append(error)
                        self.db.record_error("product", str(product.id), error)
                    elif action == "created":
                        result.created += 1
                    elif action == "updated":
                        result.updated += 1
                    elif action == "skipped":
                        result.skipped += 1

                except Exception as e:
                    error_msg = f"Product {product.id}: {str(e)}"
                    logger.error(error_msg)
                    result.errors.append(error_msg)
                    self.db.record_error("product", str(product.id), str(e))

        except Exception as e:
            logger.error(f"Failed to fetch products: {e}")
            result.errors.append(f"Fetch failed: {str(e)}")
            result.success = False

        logger.info(
            f"Product sync complete: "
            f"{result.created} created, {result.updated} updated, "
            f"{result.skipped} skipped, {len(result.errors)} errors"
        )

        return result

    async def _sync_single_product(
        self,
        product: ShopifyProduct,
    ) -> Tuple[str, Optional[str]]:
        """Sync a single product to Xero."""
        shopify_id = str(product.id)

        # Convert to Xero item - returns None if no SKU
        xero_item = shopify_product_to_xero_item(product)
        if not xero_item:
            logger.debug(f"Product {shopify_id} has no SKU, skipping")
            return ("skipped", None)

        new_checksum = calculate_product_checksum(product)

        # Check existing mapping
        mapping = self.db.get_mapping(shopify_id)

        if mapping:
            # Entity exists - check if changed
            if not has_changed(mapping.checksum, new_checksum):
                logger.debug(f"Product {shopify_id} unchanged, skipping")
                return ("skipped", None)

            # Changed - update in Xero
            return await self._update_product_in_xero(
                product, xero_item, mapping, new_checksum
            )
        else:
            # New entity - check for duplicates by SKU
            return await self._create_product_in_xero(
                product, xero_item, new_checksum
            )

    async def _create_product_in_xero(
        self,
        product: ShopifyProduct,
        xero_item: XeroItem,
        checksum: str,
    ) -> Tuple[str, Optional[str]]:
        """Create a new product in Xero (with duplicate checking by SKU)."""
        shopify_id = str(product.id)

        # Check for existing item in Xero by SKU (duplicate prevention)
        existing_item = None
        try:
            existing_item = await self.xero.find_item_by_code(xero_item.Code)
        except XeroAPIError as e:
            logger.warning(f"Failed to search for existing item: {e}")

        if existing_item:
            # Found existing Xero item - link it and update if needed
            logger.info(
                f"Found existing Xero item for SKU {xero_item.Code}: "
                f"{existing_item.ItemID}"
            )
            
            # Create mapping
            mapping = SyncMapping(
                shopify_id=shopify_id,
                xero_id=existing_item.ItemID,
                entity_type="product",
                last_synced_at=datetime.utcnow(),
                shopify_updated_at=product.updated_at,
                checksum=checksum,
            )
            self.db.upsert_mapping(mapping)
            self.db.clear_error(shopify_id)
            
            # Now update the existing item with current Shopify data
            # This ensures Xero has the latest information
            xero_item.ItemID = existing_item.ItemID
            
            if self.dry_run:
                logger.info(f"[DRY RUN] Would update existing item: {xero_item.Code}")
                return ("updated", None)
            
            try:
                await self.xero.update_item(xero_item)
                logger.info(f"Updated existing Xero item for product {shopify_id} (SKU: {xero_item.Code})")
                return ("updated", None)
            except XeroAPIError as e:
                error_msg = f"Failed to update existing item for product {shopify_id}: {e}"
                logger.error(error_msg)
                return ("skipped", error_msg)

        if self.dry_run:
            logger.info(f"[DRY RUN] Would create item: {xero_item.Code} - {xero_item.Name}")
            return ("created", None)

        try:
            created_item = await self.xero.create_item(xero_item)

            # Save mapping
            mapping = SyncMapping(
                shopify_id=shopify_id,
                xero_id=created_item.ItemID,
                entity_type="product",
                last_synced_at=datetime.utcnow(),
                shopify_updated_at=product.updated_at,
                checksum=checksum,
            )
            self.db.upsert_mapping(mapping)
            self.db.clear_error(shopify_id)

            logger.info(f"Created Xero item for product {shopify_id} (SKU: {xero_item.Code})")
            return ("created", None)

        except XeroAPIError as e:
            error_msg = f"Failed to create item for product {shopify_id}: {e}"
            logger.error(error_msg)
            return ("skipped", error_msg)

    async def _update_product_in_xero(
        self,
        product: ShopifyProduct,
        xero_item: XeroItem,
        mapping: SyncMapping,
        new_checksum: str,
    ) -> Tuple[str, Optional[str]]:
        """Update an existing product in Xero.
        
        If the SKU has changed, archives the old item and creates a new one.
        """
        shopify_id = str(product.id)

        # Check if SKU has changed by fetching the current Xero item
        try:
            current_xero_item = await self.xero.get_item_by_id(mapping.xero_id)
            
            if current_xero_item and current_xero_item.Code != xero_item.Code:
                # SKU has changed! Archive old item and create new one
                logger.warning(
                    f"SKU changed for product {shopify_id}: "
                    f"{current_xero_item.Code} → {xero_item.Code}"
                )
                
                if not self.dry_run:
                    # Archive the old item by making it inactive
                    try:
                        current_xero_item.IsSold = False
                        current_xero_item.IsPurchased = False
                        current_xero_item.Name = f"[ARCHIVED] {current_xero_item.Name}"
                        await self.xero.update_item(current_xero_item)
                        logger.info(f"Archived old Xero item {mapping.xero_id} (old SKU: {current_xero_item.Code})")
                    except XeroAPIError as e:
                        logger.error(f"Failed to archive old item: {e}")
                    
                    # Create new item with new SKU
                    try:
                        created_item = await self.xero.create_item(xero_item)
                        
                        # Update mapping to point to new item
                        mapping.xero_id = created_item.ItemID
                        mapping.last_synced_at = datetime.utcnow()
                        mapping.shopify_updated_at = product.updated_at
                        mapping.checksum = new_checksum
                        self.db.upsert_mapping(mapping)
                        self.db.clear_error(shopify_id)
                        
                        logger.info(
                            f"Created new Xero item for product {shopify_id} "
                            f"with new SKU: {xero_item.Code}"
                        )
                        return ("created", None)
                    except XeroAPIError as e:
                        error_msg = f"Failed to create new item after SKU change: {e}"
                        logger.error(error_msg)
                        return ("skipped", error_msg)
                else:
                    logger.info(
                        f"[DRY RUN] Would archive item {current_xero_item.Code} "
                        f"and create new item {xero_item.Code}"
                    )
                    return ("updated", None)
        
        except XeroAPIError as e:
            logger.warning(f"Could not fetch current item to check SKU: {e}")
            # Continue with normal update
        
        # Normal update (no SKU change)
        xero_item.ItemID = mapping.xero_id

        if self.dry_run:
            logger.info(f"[DRY RUN] Would update item: {xero_item.Code}")
            return ("updated", None)

        try:
            await self.xero.update_item(xero_item)

            # Update mapping
            mapping.last_synced_at = datetime.utcnow()
            mapping.shopify_updated_at = product.updated_at
            mapping.checksum = new_checksum
            self.db.upsert_mapping(mapping)
            self.db.clear_error(shopify_id)

            logger.info(f"Updated Xero item for product {shopify_id}")
            return ("updated", None)

        except XeroAPIError as e:
            error_msg = f"Failed to update item for product {shopify_id}: {e}"
            logger.error(error_msg)
            return ("skipped", error_msg)

    # =========================================================================
    # ORDER SYNC
    # =========================================================================

    async def sync_orders(self, force: bool = False) -> SyncResult:
        """Sync all orders from Shopify to Xero as invoices.

        Args:
            force: If True, sync all orders regardless of last sync time

        Returns:
            SyncResult with counts of created/updated/skipped/errors
        """
        result = SyncResult(success=True)

        try:
            last_sync = self.db.get_last_successful_sync()
            updated_at_min = None if force else (last_sync.completed_at if last_sync else None)

            logger.info(
                f"Fetching orders from Shopify "
                f"(updated since: {updated_at_min or 'all time'})"
            )

            # Build SKU to GL code mapping for line items
            sku_to_gl_code = await self._build_sku_gl_mapping()

            # Fetch orders (handles both REST and GraphQL)
            orders = await self._fetch_entities(
                self.shopify.fetch_all_orders,
                updated_at_min=updated_at_min,
                status="any"
            )
            
            for order in orders:
                try:
                    action, error = await self._sync_single_order(order, sku_to_gl_code)
                    if error:
                        result.errors.append(error)
                        self.db.record_error("order", str(order.id), error)
                    elif action == "created":
                        result.created += 1
                    elif action == "updated":
                        result.updated += 1
                    elif action == "skipped":
                        result.skipped += 1

                except Exception as e:
                    error_msg = f"Order {order.id}: {str(e)}"
                    logger.error(error_msg)
                    result.errors.append(error_msg)
                    self.db.record_error("order", str(order.id), str(e))

        except Exception as e:
            logger.error(f"Failed to fetch orders: {e}")
            result.errors.append(f"Fetch failed: {str(e)}")
            result.success = False

        logger.info(
            f"Order sync complete: "
            f"{result.created} created, {result.updated} updated, "
            f"{result.skipped} skipped, {len(result.errors)} errors"
        )

        return result

    async def _build_sku_gl_mapping(self) -> Dict[str, str]:
        """Build a mapping of SKU to GL account code from synced products.

        Returns:
            Dict mapping SKU to GL account code
        """
        from .constants import get_gl_codes_for_category, DEFAULT_GL_MAPPING

        sku_to_gl = {}

        # Get all product mappings
        product_mappings = self.db.get_all_mappings(entity_type="product")

        for mapping in product_mappings:
            try:
                # We don't have the product category stored, so use default
                # In a more complete implementation, we'd store category in mapping
                sku_to_gl[mapping.shopify_id] = DEFAULT_GL_MAPPING.sales_account
            except Exception:
                continue

        return sku_to_gl

    async def _sync_single_order(
        self,
        order: ShopifyOrder,
        sku_to_gl_code: Dict[str, str],
    ) -> Tuple[str, Optional[str]]:
        """Sync a single order to Xero as an invoice."""
        shopify_id = str(order.id)
        new_checksum = calculate_order_checksum(order)

        # Check existing mapping
        mapping = self.db.get_mapping(shopify_id)

        if mapping:
            # Order already synced - check if changed
            if not has_changed(mapping.checksum, new_checksum):
                logger.debug(f"Order {shopify_id} unchanged, skipping")
                return ("skipped", None)

            # Orders/invoices typically shouldn't be updated after creation
            # Just update the checksum to note we've seen the change
            logger.info(f"Order {shopify_id} changed but invoice already exists, skipping update")
            mapping.checksum = new_checksum
            mapping.last_synced_at = datetime.utcnow()
            self.db.upsert_mapping(mapping)
            return ("skipped", None)
        else:
            # New order - create invoice
            return await self._create_order_in_xero(order, sku_to_gl_code, new_checksum)

    async def _create_order_in_xero(
        self,
        order: ShopifyOrder,
        sku_to_gl_code: Dict[str, str],
        checksum: str,
    ) -> Tuple[str, Optional[str]]:
        """Create a new order as invoice in Xero."""
        shopify_id = str(order.id)
        from .constants import INVOICE_REFERENCE_PREFIX

        # Build reference for duplicate check
        reference = f"{INVOICE_REFERENCE_PREFIX}{order.order_number}"

        # Check for existing invoice by reference (duplicate prevention)
        existing_invoice = None
        try:
            existing_invoice = await self.xero.find_invoice_by_reference(reference)
        except XeroAPIError as e:
            logger.warning(f"Failed to search for existing invoice: {e}")

        if existing_invoice:
            # Link to existing invoice instead of creating duplicate
            logger.info(
                f"Found existing Xero invoice for order {order.order_number}: "
                f"{existing_invoice.InvoiceID}"
            )
            mapping = SyncMapping(
                shopify_id=shopify_id,
                xero_id=existing_invoice.InvoiceID,
                entity_type="order",
                last_synced_at=datetime.utcnow(),
                shopify_updated_at=order.updated_at,
                checksum=checksum,
            )
            self.db.upsert_mapping(mapping)
            self.db.clear_error(shopify_id)
            return ("skipped", None)

        # Get the customer's Xero contact ID
        contact_id = await self._get_customer_contact_id(order)
        if not contact_id:
            error_msg = f"No Xero contact found for order {shopify_id}"
            logger.warning(error_msg)
            return ("skipped", error_msg)

        # Convert to Xero invoice
        xero_invoice = shopify_order_to_xero_invoice(order, contact_id, sku_to_gl_code)

        if self.dry_run:
            logger.info(f"[DRY RUN] Would create invoice: {reference}")
            return ("created", None)

        try:
            created_invoice = await self.xero.create_invoice(xero_invoice)

            # Save mapping
            mapping = SyncMapping(
                shopify_id=shopify_id,
                xero_id=created_invoice.InvoiceID,
                entity_type="order",
                last_synced_at=datetime.utcnow(),
                shopify_updated_at=order.updated_at,
                checksum=checksum,
            )
            self.db.upsert_mapping(mapping)
            self.db.clear_error(shopify_id)

            logger.info(f"Created Xero invoice for order {order.order_number}")
            return ("created", None)

        except XeroAPIError as e:
            error_msg = f"Failed to create invoice for order {shopify_id}: {e}"
            logger.error(error_msg)
            return ("skipped", error_msg)

    async def _get_customer_contact_id(self, order: ShopifyOrder) -> Optional[str]:
        """Get the Xero contact ID for an order's customer.

        Looks up by:
        1. Existing mapping from order.customer.id
        2. Email search in Xero

        Args:
            order: Shopify order

        Returns:
            Xero ContactID or None if not found
        """
        # Try to find by customer ID mapping
        if order.customer and order.customer.id:
            mapping = self.db.get_mapping(str(order.customer.id))
            if mapping and mapping.entity_type == "customer":
                return mapping.xero_id

        # Try to find by email
        email = order.email or (order.customer.email if order.customer else None)
        if email:
            try:
                contact = await self.xero.find_contact_by_email(email)
                if contact:
                    return contact.ContactID
            except XeroAPIError:
                pass

        return None

    # =========================================================================
    # RETRY & UTILITIES
    # =========================================================================

    async def _update_customer_email_marketing(self, customer_id: int) -> None:
        """Update a customer's email marketing consent in Shopify.

        Args:
            customer_id: Shopify customer ID

        Raises:
            ShopifyAPIError: On API errors
        """
        if self.dry_run:
            logger.debug(f"[DRY RUN] Would enable email marketing for customer {customer_id}")
            return

        await self.shopify.update_customer_email_marketing(customer_id, accepts_marketing=True)

    async def enable_email_marketing_for_all_customers(self) -> SyncResult:
        """Enable email marketing for all customers in Shopify.

        This is useful for migrating from another platform where email
        marketing consent wasn't properly transferred.

        Uses efficient batch processing to minimize API calls and avoid rate limits.
        Only updates customers who are NOT already subscribed.

        Returns:
            SyncResult with counts of updated/skipped/errors
        """
        result = SyncResult(success=True)

        logger.info("=" * 50)
        logger.info("ENABLING EMAIL MARKETING FOR ALL CUSTOMERS")
        logger.info("=" * 50)

        if self.dry_run:
            logger.info("DRY RUN MODE - No changes will be made to Shopify")

        try:
            # Fetch all customers
            logger.info("Fetching all customers from Shopify...")
            customers = await self._fetch_entities(self.shopify.fetch_all_customers)

            logger.info(f"Found {len(customers)} total customers")

            # Filter to only customers who are NOT subscribed
            customers_to_update = [
                customer for customer in customers
                if not customer.is_subscribed_to_email_marketing
            ]

            result.skipped = len(customers) - len(customers_to_update)

            logger.info(
                f"Found {len(customers_to_update)} customers to update "
                f"({result.skipped} already subscribed)"
            )

            if not customers_to_update:
                logger.info("All customers are already subscribed!")
                return result

            if self.dry_run:
                # In dry run, just show what would be updated
                for customer in customers_to_update:
                    logger.info(
                        f"[DRY RUN] Would enable email marketing for customer {customer.id} "
                        f"({customer.email or 'no email'})"
                    )
                    result.updated += 1
                    await asyncio.sleep(0.01)  # Small delay for readability
            else:
                # Use batch operations for efficiency
                from .shopify_graphql_client import ShopifyGraphQLClient
                from .shopify_bulk_operations import ShopifyBulkOperations

                # Check if we're using GraphQL client
                if isinstance(self.shopify, ShopifyGraphQLClient):
                    logger.info("Using batch operations for efficient updates...")

                    # Extract customer IDs
                    customer_ids = [customer.id for customer in customers_to_update]

                    # Use bulk operations handler
                    bulk_ops = ShopifyBulkOperations(self.shopify)
                    batch_result = await bulk_ops.batch_update_customer_email_marketing(
                        customer_ids=customer_ids,
                        accepts_marketing=True,
                        batch_size=50  # Process 50 at a time
                    )

                    result.updated = batch_result['updated']
                    result.errors = batch_result['errors']
                    result.success = batch_result['success']

                    logger.info(
                        f"Batch update completed in {batch_result['duration']:.1f}s: "
                        f"{batch_result['updated']} updated, {batch_result['failed']} failed"
                    )
                else:
                    # Fallback to individual updates for REST API
                    logger.info("Using individual updates (REST API)...")
                    for customer in customers_to_update:
                        try:
                            await self.shopify.update_customer_email_marketing(
                                customer.id,
                                accepts_marketing=True
                            )
                            logger.info(
                                f"Enabled email marketing for customer {customer.id} "
                                f"({customer.email or 'no email'})"
                            )
                            result.updated += 1

                            # Add small delay to respect rate limits
                            await asyncio.sleep(0.5)

                        except Exception as e:
                            error_msg = f"Customer {customer.id}: {str(e)}"
                            logger.error(error_msg)
                            result.errors.append(error_msg)

        except Exception as e:
            logger.error(f"Failed to fetch customers: {e}")
            result.errors.append(f"Fetch failed: {str(e)}")
            result.success = False

        logger.info("=" * 50)
        logger.info(
            f"Email marketing update complete: "
            f"{result.updated} updated, {result.skipped} already subscribed, "
            f"{len(result.errors)} errors"
        )
        logger.info("=" * 50)

        return result

    async def retry_failed_syncs(self) -> SyncResult:
        """Retry previously failed sync operations.

        Returns:
            SyncResult with retry outcomes
        """
        result = SyncResult(success=True)

        # Get errors eligible for retry
        errors = self.db.get_errors(max_retry_count=self.settings.max_retries)

        if not errors:
            logger.info("No failed syncs to retry")
            return result

        logger.info(f"Retrying {len(errors)} failed sync operations")

        for error in errors:
            try:
                if error.entity_type == "customer":
                    customer = await self.shopify.get_customer(int(error.shopify_id))
                    if customer:
                        action, err = await self._sync_single_customer(customer)
                        self._update_retry_result(result, action, err)
                    else:
                        self.db.clear_error(error.shopify_id)
                        result.skipped += 1

                elif error.entity_type == "product":
                    # Fetch product and retry
                    products = await self.shopify.fetch_products(limit=1)
                    # Note: Would need get_product method for proper retry
                    self.db.clear_error(error.shopify_id)
                    result.skipped += 1

                elif error.entity_type == "order":
                    # Fetch order and retry
                    # Note: Would need get_order method for proper retry
                    self.db.clear_error(error.shopify_id)
                    result.skipped += 1

            except Exception as e:
                error_msg = f"Retry failed for {error.entity_type} {error.shopify_id}: {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)

        logger.info(
            f"Retry complete: {result.created} created, {result.updated} updated, "
            f"{result.skipped} skipped, {len(result.errors)} still failing"
        )

        return result

    def _update_retry_result(
        self,
        result: SyncResult,
        action: str,
        error: Optional[str],
    ) -> None:
        """Update retry result based on sync action."""
        if error:
            result.errors.append(error)
        elif action == "created":
            result.created += 1
        elif action == "updated":
            result.updated += 1
        elif action == "skipped":
            result.skipped += 1

    async def verify_connections(self) -> Tuple[bool, bool]:
        """Verify both API connections are working.

        Returns:
            Tuple of (shopify_ok, xero_ok)
        """
        shopify_ok = await self.shopify.check_connection()
        xero_ok = await self.xero.check_connection()

        if not shopify_ok:
            logger.error("Shopify API connection failed")
        if not xero_ok:
            logger.error("Xero API connection failed")

        return (shopify_ok, xero_ok)

    def get_sync_stats(self) -> dict:
        """Get current sync statistics from database.

        Returns:
            Dictionary with sync statistics
        """
        return self.db.get_stats()
