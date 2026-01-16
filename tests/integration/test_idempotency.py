"""Integration tests for idempotent sync behavior.

Tests verify that:
- Running sync multiple times produces consistent results
- No duplicate records are created in Xero
- Unchanged entities are skipped efficiently
- Database state remains consistent across syncs
"""

import pytest
import pytest_asyncio
from datetime import datetime
from unittest.mock import AsyncMock

from src.sync_engine import SyncEngine, SyncResult
from src.database import Database
from src.shopify_client import ShopifyClient
from src.xero_client import XeroClient
from src.config import Settings
from src.models import (
    ShopifyCustomer,
    ShopifyAddress,
    ShopifyProduct,
    ShopifyProductVariant,
    XeroContact,
    XeroItem,
    SyncMapping,
)
from src.checksums import calculate_customer_checksum


@pytest.fixture
def mock_settings(mock_env_vars):
    """Create settings with mock environment variables."""
    return Settings()


@pytest.fixture
def database(temp_db_path):
    """Create a real database for integration testing."""
    return Database(temp_db_path)


@pytest.fixture
def mock_shopify_client(mock_settings):
    """Create a mock Shopify client."""
    client = AsyncMock(spec=ShopifyClient)
    client.settings = mock_settings
    return client


@pytest.fixture
def mock_xero_client(mock_settings):
    """Create a mock Xero client."""
    client = AsyncMock(spec=XeroClient)
    client.settings = mock_settings
    return client


@pytest.fixture
def sync_engine(mock_settings, database, mock_shopify_client, mock_xero_client):
    """Create a sync engine for integration testing."""
    return SyncEngine(
        settings=mock_settings,
        database=database,
        shopify_client=mock_shopify_client,
        xero_client=mock_xero_client,
        dry_run=False,
    )


class TestIdempotentCustomerSync:
    """Integration tests for idempotent customer sync."""

    @pytest.mark.asyncio
    async def test_first_sync_creates_customer(
        self, sync_engine, mock_xero_client, database
    ):
        """Test first sync creates new customer in Xero."""
        customer = ShopifyCustomer(
            id=1001,
            email="new.customer@example.com",
            first_name="New",
            last_name="Customer",
            phone="+441234567890",
        )

        # Xero has no existing contact
        mock_xero_client.find_contact_by_email.return_value = None

        # Contact creation succeeds
        created_contact = XeroContact(
            ContactID="xero-uuid-1001",
            Name="New Customer",
            EmailAddress="new.customer@example.com",
        )
        mock_xero_client.create_contact.return_value = created_contact

        action, error = await sync_engine._sync_single_customer(customer)

        assert action == "created"
        assert error is None
        mock_xero_client.create_contact.assert_called_once()

        # Verify mapping exists in database
        mapping = database.get_mapping("1001")
        assert mapping is not None
        assert mapping.xero_id == "xero-uuid-1001"
        assert mapping.entity_type == "customer"
        assert mapping.checksum is not None

    @pytest.mark.asyncio
    async def test_second_sync_skips_unchanged_customer(
        self, sync_engine, mock_xero_client, database
    ):
        """Test second sync skips customer when data hasn't changed."""
        customer = ShopifyCustomer(
            id=1002,
            email="unchanged@example.com",
            first_name="Unchanged",
            last_name="Customer",
        )

        # First sync: create the customer
        mock_xero_client.find_contact_by_email.return_value = None
        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="xero-uuid-1002",
            Name="Unchanged Customer",
        )

        action1, _ = await sync_engine._sync_single_customer(customer)
        assert action1 == "created"

        # Reset mocks to track second sync calls
        mock_xero_client.create_contact.reset_mock()
        mock_xero_client.update_contact.reset_mock()
        mock_xero_client.find_contact_by_email.reset_mock()

        # Second sync: same customer, same data
        action2, error2 = await sync_engine._sync_single_customer(customer)

        assert action2 == "skipped"
        assert error2 is None

        # Should NOT call any Xero APIs
        mock_xero_client.create_contact.assert_not_called()
        mock_xero_client.update_contact.assert_not_called()
        mock_xero_client.find_contact_by_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_updates_when_customer_changes(
        self, sync_engine, mock_xero_client, database
    ):
        """Test sync updates customer when data has changed."""
        original_customer = ShopifyCustomer(
            id=1003,
            email="changing@example.com",
            first_name="Original",
            last_name="Name",
        )

        # First sync: create
        mock_xero_client.find_contact_by_email.return_value = None
        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="xero-uuid-1003",
            Name="Original Name",
        )

        await sync_engine._sync_single_customer(original_customer)

        # Reset mocks
        mock_xero_client.reset_mock()

        # Second sync: customer data changed
        updated_customer = ShopifyCustomer(
            id=1003,
            email="changing@example.com",
            first_name="Updated",  # Changed!
            last_name="Name",
        )

        mock_xero_client.update_contact.return_value = XeroContact(
            ContactID="xero-uuid-1003",
            Name="Updated Name",
        )

        action, error = await sync_engine._sync_single_customer(updated_customer)

        assert action == "updated"
        assert error is None
        mock_xero_client.update_contact.assert_called_once()
        mock_xero_client.create_contact.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_syncs_maintain_single_mapping(
        self, sync_engine, mock_xero_client, database
    ):
        """Test multiple syncs maintain exactly one mapping per customer."""
        customer = ShopifyCustomer(
            id=1004,
            email="multisync@example.com",
            first_name="Multi",
            last_name="Sync",
        )

        mock_xero_client.find_contact_by_email.return_value = None
        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="xero-uuid-1004",
            Name="Multi Sync",
        )

        # Run sync 5 times
        for i in range(5):
            await sync_engine._sync_single_customer(customer)

        # Should only have one mapping
        mappings = database.get_all_mappings(entity_type="customer")
        customer_mappings = [m for m in mappings if m.shopify_id == "1004"]
        assert len(customer_mappings) == 1

    @pytest.mark.asyncio
    async def test_sync_with_address_change_triggers_update(
        self, sync_engine, mock_xero_client, database
    ):
        """Test sync detects address changes."""
        customer_v1 = ShopifyCustomer(
            id=1005,
            email="address@example.com",
            first_name="Address",
            last_name="Customer",
            default_address=ShopifyAddress(
                address1="123 Old Street",
                city="London",
            ),
        )

        # First sync
        mock_xero_client.find_contact_by_email.return_value = None
        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="xero-uuid-1005",
            Name="Address Customer",
        )

        await sync_engine._sync_single_customer(customer_v1)

        # Reset
        mock_xero_client.reset_mock()

        # Second sync: address changed
        customer_v2 = ShopifyCustomer(
            id=1005,
            email="address@example.com",
            first_name="Address",
            last_name="Customer",
            default_address=ShopifyAddress(
                address1="456 New Street",  # Changed!
                city="Manchester",  # Changed!
            ),
        )

        mock_xero_client.update_contact.return_value = XeroContact(
            ContactID="xero-uuid-1005",
            Name="Address Customer",
        )

        action, _ = await sync_engine._sync_single_customer(customer_v2)

        assert action == "updated"
        mock_xero_client.update_contact.assert_called_once()


class TestIdempotentFullSync:
    """Integration tests for full sync idempotency."""

    @pytest.mark.asyncio
    async def test_full_sync_twice_no_duplicates(
        self, sync_engine, mock_shopify_client, mock_xero_client, database
    ):
        """Test running full sync twice doesn't create duplicates."""
        customers = [
            ShopifyCustomer(id=2001, email="c1@example.com", first_name="C", last_name="One"),
            ShopifyCustomer(id=2002, email="c2@example.com", first_name="C", last_name="Two"),
            ShopifyCustomer(id=2003, email="c3@example.com", first_name="C", last_name="Three"),
        ]

        async def async_generator():
            for c in customers:
                yield c

        # First sync
        mock_shopify_client.fetch_all_customers.return_value = async_generator()
        mock_xero_client.find_contact_by_email.return_value = None

        contact_ids = {}
        def create_contact_side_effect(contact):
            cid = f"xero-uuid-{contact.EmailAddress}"
            contact_ids[contact.EmailAddress] = cid
            return XeroContact(ContactID=cid, Name=contact.Name)

        mock_xero_client.create_contact.side_effect = create_contact_side_effect

        result1 = await sync_engine.sync_customers()

        assert result1.created == 3
        assert result1.skipped == 0

        # Reset for second sync
        mock_xero_client.create_contact.reset_mock()
        mock_xero_client.create_contact.side_effect = create_contact_side_effect

        # Second sync - return same customers
        mock_shopify_client.fetch_all_customers.return_value = async_generator()

        result2 = await sync_engine.sync_customers()

        # Should skip all (unchanged)
        assert result2.created == 0
        assert result2.skipped == 3
        mock_xero_client.create_contact.assert_not_called()

    @pytest.mark.asyncio
    async def test_incremental_sync_after_full_sync(
        self, sync_engine, mock_shopify_client, mock_xero_client, database
    ):
        """Test incremental sync only processes new/changed customers."""
        # Initial customers
        original_customers = [
            ShopifyCustomer(id=3001, email="orig1@example.com", first_name="Orig", last_name="One"),
            ShopifyCustomer(id=3002, email="orig2@example.com", first_name="Orig", last_name="Two"),
        ]

        async def original_generator():
            for c in original_customers:
                yield c

        # First sync
        mock_shopify_client.fetch_all_customers.return_value = original_generator()
        mock_xero_client.find_contact_by_email.return_value = None

        def create_contact(contact):
            return XeroContact(
                ContactID=f"xero-{contact.Name.lower().replace(' ', '-')}",
                Name=contact.Name,
            )

        mock_xero_client.create_contact.side_effect = create_contact

        result1 = await sync_engine.sync_customers()
        assert result1.created == 2

        # Reset
        mock_xero_client.create_contact.reset_mock()

        # Add new customer for incremental sync
        updated_customers = original_customers + [
            ShopifyCustomer(id=3003, email="new@example.com", first_name="New", last_name="Customer"),
        ]

        async def updated_generator():
            for c in updated_customers:
                yield c

        mock_shopify_client.fetch_all_customers.return_value = updated_generator()

        result2 = await sync_engine.sync_customers()

        # Should create 1 new, skip 2 unchanged
        assert result2.created == 1
        assert result2.skipped == 2


class TestDatabaseStateConsistency:
    """Integration tests for database state consistency."""

    @pytest.mark.asyncio
    async def test_mapping_checksum_updates_on_change(
        self, sync_engine, mock_xero_client, database
    ):
        """Test mapping checksum is updated when customer changes."""
        customer_v1 = ShopifyCustomer(
            id=4001,
            email="checksum@example.com",
            first_name="Checksum",
            last_name="Test",
        )

        # First sync
        mock_xero_client.find_contact_by_email.return_value = None
        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="xero-4001",
            Name="Checksum Test",
        )

        await sync_engine._sync_single_customer(customer_v1)

        mapping1 = database.get_mapping("4001")
        checksum1 = mapping1.checksum

        # Update customer
        customer_v2 = ShopifyCustomer(
            id=4001,
            email="checksum@example.com",
            first_name="Updated",  # Changed
            last_name="Test",
        )

        mock_xero_client.update_contact.return_value = XeroContact(
            ContactID="xero-4001",
            Name="Updated Test",
        )

        await sync_engine._sync_single_customer(customer_v2)

        mapping2 = database.get_mapping("4001")
        checksum2 = mapping2.checksum

        # Checksums should be different
        assert checksum1 != checksum2

    @pytest.mark.asyncio
    async def test_sync_history_recorded_correctly(
        self, sync_engine, mock_shopify_client, mock_xero_client, database
    ):
        """Test sync history is recorded for each run."""
        async def empty_generator():
            return
            yield

        mock_shopify_client.fetch_all_customers.return_value = empty_generator()

        # Run 3 syncs
        for _ in range(3):
            await sync_engine.run_full_sync()

        history = database.get_sync_history(limit=10)
        assert len(history) == 3

        # All should be successful
        for entry in history:
            assert entry.status == "success"

    @pytest.mark.asyncio
    async def test_mapping_timestamps_updated(
        self, sync_engine, mock_xero_client, database
    ):
        """Test mapping timestamps are updated on sync."""
        import time

        customer = ShopifyCustomer(
            id=4002,
            email="timestamp@example.com",
            first_name="Timestamp",
            last_name="Test",
        )

        mock_xero_client.find_contact_by_email.return_value = None
        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="xero-4002",
            Name="Timestamp Test",
        )

        await sync_engine._sync_single_customer(customer)

        mapping1 = database.get_mapping("4002")
        time1 = mapping1.last_synced_at

        # Wait briefly
        time.sleep(0.1)

        # Force an update by changing data
        customer.first_name = "Changed"
        mock_xero_client.update_contact.return_value = XeroContact(
            ContactID="xero-4002",
            Name="Changed Test",
        )

        await sync_engine._sync_single_customer(customer)

        mapping2 = database.get_mapping("4002")
        time2 = mapping2.last_synced_at

        # Timestamp should be updated
        assert time2 > time1


class TestEdgeCases:
    """Integration tests for edge cases in idempotent sync."""

    @pytest.mark.asyncio
    async def test_customer_without_email_creates_each_time(
        self, sync_engine, mock_xero_client, database
    ):
        """Test customer without email still works (no email-based duplicate check)."""
        customer = ShopifyCustomer(
            id=5001,
            email=None,
            first_name="No",
            last_name="Email",
        )

        mock_xero_client.find_contact_by_email.return_value = None
        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="xero-5001",
            Name="No Email",
        )

        action, _ = await sync_engine._sync_single_customer(customer)

        assert action == "created"

        # Second sync should skip (mapping exists with matching checksum)
        mock_xero_client.reset_mock()

        action2, _ = await sync_engine._sync_single_customer(customer)

        assert action2 == "skipped"

    @pytest.mark.asyncio
    async def test_concurrent_mapping_updates(
        self, mock_settings, temp_db_path, mock_shopify_client, mock_xero_client
    ):
        """Test that concurrent mapping updates are handled correctly."""
        import asyncio

        # Create two separate database instances (simulating concurrent access)
        db1 = Database(temp_db_path)
        db2 = Database(temp_db_path)

        engine1 = SyncEngine(mock_settings, db1, mock_shopify_client, mock_xero_client)
        engine2 = SyncEngine(mock_settings, db2, mock_shopify_client, mock_xero_client)

        customer = ShopifyCustomer(
            id=5002,
            email="concurrent@example.com",
            first_name="Concurrent",
            last_name="Test",
        )

        mock_xero_client.find_contact_by_email.return_value = None
        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="xero-5002",
            Name="Concurrent Test",
        )

        # Run both syncs - they should handle the same customer gracefully
        await engine1._sync_single_customer(customer)

        # Second engine should see the existing mapping
        action, _ = await engine2._sync_single_customer(customer)

        # Should skip because mapping now exists
        assert action == "skipped"
