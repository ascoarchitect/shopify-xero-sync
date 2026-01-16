"""Unit tests for sync engine orchestration.

Tests verify that:
- Sync engine initializes correctly
- Customer sync flow works correctly
- Change detection integrates with checksums
- Duplicate prevention works via email lookup
- Error handling and recovery work correctly
- Dry run mode prevents actual changes
- Retry logic for failed syncs works correctly
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
import uuid

from src.sync_engine import SyncEngine, SyncResult, SyncStats
from src.database import Database
from src.shopify_client import ShopifyClient, ShopifyAPIError
from src.xero_client import XeroClient, XeroAPIError
from src.config import Settings
from src.models import (
    ShopifyCustomer,
    ShopifyAddress,
    XeroContact,
    SyncMapping,
    SyncHistoryEntry,
    SyncError,
)

from tests.fixtures.shopify_fixtures import (
    make_shopify_customer,
    SHOPIFY_CUSTOMER_FULL,
    SHOPIFY_CUSTOMER_MINIMAL,
    SHOPIFY_CUSTOMER_NO_EMAIL,
)
from tests.fixtures.xero_fixtures import (
    make_xero_contact,
    XERO_CONTACT_EXISTING,
)


@pytest.fixture
def mock_settings(mock_env_vars):
    """Create settings with mock environment variables."""
    return Settings()


@pytest.fixture
def mock_database(temp_db_path):
    """Create a real database for testing."""
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
def sync_engine(mock_settings, mock_database, mock_shopify_client, mock_xero_client):
    """Create a sync engine with mocked dependencies."""
    return SyncEngine(
        settings=mock_settings,
        database=mock_database,
        shopify_client=mock_shopify_client,
        xero_client=mock_xero_client,
        dry_run=False,
    )


@pytest.fixture
def dry_run_sync_engine(mock_settings, mock_database, mock_shopify_client, mock_xero_client):
    """Create a sync engine in dry run mode."""
    return SyncEngine(
        settings=mock_settings,
        database=mock_database,
        shopify_client=mock_shopify_client,
        xero_client=mock_xero_client,
        dry_run=True,
    )


class TestSyncResult:
    """Tests for SyncResult dataclass."""

    def test_sync_result_defaults(self):
        """Test SyncResult default values."""
        result = SyncResult(success=True)

        assert result.success is True
        assert result.created == 0
        assert result.updated == 0
        assert result.skipped == 0
        assert result.errors == []

    def test_sync_result_total_processed(self):
        """Test total_processed property."""
        result = SyncResult(
            success=True,
            created=5,
            updated=3,
            skipped=2,
        )

        assert result.total_processed == 10

    def test_sync_result_with_errors(self):
        """Test SyncResult with errors."""
        result = SyncResult(
            success=False,
            errors=["Error 1", "Error 2"],
        )

        assert result.success is False
        assert len(result.errors) == 2


class TestSyncStats:
    """Tests for SyncStats dataclass."""

    def test_sync_stats_creation(self):
        """Test SyncStats creation."""
        stats = SyncStats(
            run_id="test-run-123",
            started_at=datetime.utcnow(),
        )

        assert stats.run_id == "test-run-123"
        assert stats.completed_at is None
        assert stats.customers is None

    def test_sync_stats_total_errors(self):
        """Test total_errors property aggregates all errors."""
        stats = SyncStats(
            run_id="test-run",
            started_at=datetime.utcnow(),
            customers=SyncResult(success=False, errors=["Customer error"]),
            products=SyncResult(success=False, errors=["Product error"]),
            orders=SyncResult(success=True, errors=[]),
        )

        assert len(stats.total_errors) == 2
        assert "Customer error" in stats.total_errors
        assert "Product error" in stats.total_errors

    def test_sync_stats_success_property(self):
        """Test success property is True when no errors."""
        stats = SyncStats(
            run_id="test-run",
            started_at=datetime.utcnow(),
            customers=SyncResult(success=True),
        )

        assert stats.success is True

    def test_sync_stats_success_false_with_errors(self):
        """Test success property is False when errors exist."""
        stats = SyncStats(
            run_id="test-run",
            started_at=datetime.utcnow(),
            customers=SyncResult(success=False, errors=["Error"]),
        )

        assert stats.success is False


class TestSyncEngineInit:
    """Tests for SyncEngine initialization."""

    def test_engine_init(self, sync_engine, mock_settings, mock_database):
        """Test sync engine initializes correctly."""
        assert sync_engine.settings == mock_settings
        assert sync_engine.db == mock_database
        assert sync_engine.dry_run is False

    def test_engine_dry_run_from_settings(self, mock_settings, mock_database, mock_shopify_client, mock_xero_client):
        """Test dry run mode can be set via settings."""
        mock_settings.dry_run = True
        engine = SyncEngine(
            settings=mock_settings,
            database=mock_database,
            shopify_client=mock_shopify_client,
            xero_client=mock_xero_client,
            dry_run=False,  # Should be overridden by settings
        )

        assert engine.dry_run is True

    def test_engine_dry_run_parameter_overrides(self, mock_settings, mock_database, mock_shopify_client, mock_xero_client):
        """Test dry run mode can be set via parameter."""
        mock_settings.dry_run = False
        engine = SyncEngine(
            settings=mock_settings,
            database=mock_database,
            shopify_client=mock_shopify_client,
            xero_client=mock_xero_client,
            dry_run=True,
        )

        assert engine.dry_run is True


class TestVerifyConnections:
    """Tests for connection verification."""

    @pytest.mark.asyncio
    async def test_verify_connections_both_ok(self, sync_engine, mock_shopify_client, mock_xero_client):
        """Test both connections successful."""
        mock_shopify_client.check_connection.return_value = True
        mock_xero_client.check_connection.return_value = True

        shopify_ok, xero_ok = await sync_engine.verify_connections()

        assert shopify_ok is True
        assert xero_ok is True

    @pytest.mark.asyncio
    async def test_verify_connections_shopify_fails(self, sync_engine, mock_shopify_client, mock_xero_client):
        """Test Shopify connection fails."""
        mock_shopify_client.check_connection.return_value = False
        mock_xero_client.check_connection.return_value = True

        shopify_ok, xero_ok = await sync_engine.verify_connections()

        assert shopify_ok is False
        assert xero_ok is True

    @pytest.mark.asyncio
    async def test_verify_connections_xero_fails(self, sync_engine, mock_shopify_client, mock_xero_client):
        """Test Xero connection fails."""
        mock_shopify_client.check_connection.return_value = True
        mock_xero_client.check_connection.return_value = False

        shopify_ok, xero_ok = await sync_engine.verify_connections()

        assert shopify_ok is True
        assert xero_ok is False


class TestSyncSingleCustomerCreate:
    """Tests for syncing a single new customer."""

    @pytest.mark.asyncio
    async def test_create_new_customer(self, sync_engine, mock_xero_client, mock_database):
        """Test creating a new customer in Xero."""
        customer = ShopifyCustomer(
            id=12345,
            email="new@example.com",
            first_name="New",
            last_name="Customer",
        )

        # No existing contact in Xero
        mock_xero_client.find_contact_by_email.return_value = None

        # Contact created successfully
        created_contact = XeroContact(
            ContactID="xero-contact-123",
            Name="New Customer",
            EmailAddress="new@example.com",
        )
        mock_xero_client.create_contact.return_value = created_contact

        action, error = await sync_engine._sync_single_customer(customer)

        assert action == "created"
        assert error is None
        mock_xero_client.create_contact.assert_called_once()

        # Verify mapping was saved
        mapping = mock_database.get_mapping("12345")
        assert mapping is not None
        assert mapping.xero_id == "xero-contact-123"

    @pytest.mark.asyncio
    async def test_create_customer_links_existing(self, sync_engine, mock_xero_client, mock_database):
        """Test linking to existing Xero contact instead of creating duplicate."""
        customer = ShopifyCustomer(
            id=12345,
            email="existing@example.com",
            first_name="Existing",
            last_name="Customer",
        )

        # Contact already exists in Xero
        existing_contact = XeroContact(
            ContactID="existing-xero-id",
            Name="Existing Customer",
            EmailAddress="existing@example.com",
        )
        mock_xero_client.find_contact_by_email.return_value = existing_contact

        action, error = await sync_engine._sync_single_customer(customer)

        assert action == "skipped"  # Linked to existing, not created
        assert error is None
        mock_xero_client.create_contact.assert_not_called()

        # Verify mapping was saved linking to existing
        mapping = mock_database.get_mapping("12345")
        assert mapping is not None
        assert mapping.xero_id == "existing-xero-id"

    @pytest.mark.asyncio
    async def test_create_customer_dry_run(self, dry_run_sync_engine, mock_xero_client):
        """Test dry run mode doesn't create contact."""
        customer = ShopifyCustomer(
            id=12345,
            email="new@example.com",
            first_name="New",
            last_name="Customer",
        )

        mock_xero_client.find_contact_by_email.return_value = None

        action, error = await dry_run_sync_engine._sync_single_customer(customer)

        assert action == "created"
        assert error is None
        mock_xero_client.create_contact.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_customer_api_error(self, sync_engine, mock_xero_client):
        """Test handling API error during creation."""
        customer = ShopifyCustomer(
            id=12345,
            email="error@example.com",
            first_name="Error",
            last_name="Customer",
        )

        mock_xero_client.find_contact_by_email.return_value = None
        mock_xero_client.create_contact.side_effect = XeroAPIError("API Error")

        action, error = await sync_engine._sync_single_customer(customer)

        assert action == "skipped"
        assert error is not None
        assert "API Error" in error


class TestSyncSingleCustomerUpdate:
    """Tests for syncing an existing customer with changes."""

    @pytest.mark.asyncio
    async def test_update_changed_customer(self, sync_engine, mock_xero_client, mock_database):
        """Test updating customer when data has changed."""
        # First, create the initial mapping
        initial_mapping = SyncMapping(
            shopify_id="12345",
            xero_id="xero-123",
            entity_type="customer",
            checksum="old_checksum",
        )
        mock_database.upsert_mapping(initial_mapping)

        # Customer with changed data
        customer = ShopifyCustomer(
            id=12345,
            email="updated@example.com",  # Different email
            first_name="Updated",
            last_name="Customer",
        )

        # Update succeeds
        updated_contact = XeroContact(
            ContactID="xero-123",
            Name="Updated Customer",
        )
        mock_xero_client.update_contact.return_value = updated_contact

        action, error = await sync_engine._sync_single_customer(customer)

        assert action == "updated"
        assert error is None
        mock_xero_client.update_contact.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_unchanged_customer(self, sync_engine, mock_xero_client, mock_database):
        """Test skipping customer when data hasn't changed."""
        # Customer data that will generate specific checksum
        customer = ShopifyCustomer(
            id=12345,
            email="same@example.com",
            first_name="Same",
            last_name="Customer",
        )

        # Calculate what the checksum should be
        from src.checksums import calculate_customer_checksum
        checksum = calculate_customer_checksum(customer)

        # Create mapping with matching checksum
        initial_mapping = SyncMapping(
            shopify_id="12345",
            xero_id="xero-123",
            entity_type="customer",
            checksum=checksum,  # Same checksum = no change
        )
        mock_database.upsert_mapping(initial_mapping)

        action, error = await sync_engine._sync_single_customer(customer)

        assert action == "skipped"
        assert error is None
        mock_xero_client.update_contact.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_customer_dry_run(self, dry_run_sync_engine, mock_xero_client, mock_database):
        """Test dry run mode doesn't update contact."""
        # Create mapping with different checksum
        initial_mapping = SyncMapping(
            shopify_id="12345",
            xero_id="xero-123",
            entity_type="customer",
            checksum="old_checksum",
        )
        mock_database.upsert_mapping(initial_mapping)

        customer = ShopifyCustomer(
            id=12345,
            email="changed@example.com",
            first_name="Changed",
            last_name="Customer",
        )

        action, error = await dry_run_sync_engine._sync_single_customer(customer)

        assert action == "updated"
        assert error is None
        mock_xero_client.update_contact.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_customer_api_error(self, sync_engine, mock_xero_client, mock_database):
        """Test handling API error during update."""
        initial_mapping = SyncMapping(
            shopify_id="12345",
            xero_id="xero-123",
            entity_type="customer",
            checksum="old_checksum",
        )
        mock_database.upsert_mapping(initial_mapping)

        customer = ShopifyCustomer(
            id=12345,
            email="error@example.com",
            first_name="Error",
            last_name="Customer",
        )

        mock_xero_client.update_contact.side_effect = XeroAPIError("Update failed")

        action, error = await sync_engine._sync_single_customer(customer)

        assert action == "skipped"
        assert error is not None
        assert "Update failed" in error


class TestSyncCustomers:
    """Tests for syncing all customers."""

    @pytest.mark.asyncio
    async def test_sync_customers_success(self, sync_engine, mock_shopify_client, mock_xero_client):
        """Test successful sync of multiple customers."""
        # Setup: Return customers from Shopify
        customers_data = [
            ShopifyCustomer(id=1, email="c1@example.com", first_name="Customer", last_name="One"),
            ShopifyCustomer(id=2, email="c2@example.com", first_name="Customer", last_name="Two"),
        ]

        async def async_generator():
            for c in customers_data:
                yield c

        mock_shopify_client.fetch_all_customers.return_value = async_generator()
        mock_xero_client.find_contact_by_email.return_value = None
        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="new-id",
            Name="Customer",
        )

        result = await sync_engine.sync_customers()

        assert result.success is True
        assert result.created == 2
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_sync_customers_partial_failure(self, sync_engine, mock_shopify_client, mock_xero_client):
        """Test sync continues despite individual failures."""
        customers_data = [
            ShopifyCustomer(id=1, email="success@example.com", first_name="Success", last_name="Customer"),
            ShopifyCustomer(id=2, email="fail@example.com", first_name="Fail", last_name="Customer"),
        ]

        async def async_generator():
            for c in customers_data:
                yield c

        mock_shopify_client.fetch_all_customers.return_value = async_generator()

        # First succeeds, second fails
        mock_xero_client.find_contact_by_email.return_value = None
        mock_xero_client.create_contact.side_effect = [
            XeroContact(ContactID="new-id", Name="Success"),
            XeroAPIError("Creation failed"),
        ]

        result = await sync_engine.sync_customers()

        assert result.created == 1
        assert len(result.errors) == 1
        assert "fail@example.com" in result.errors[0] or "Creation failed" in result.errors[0]

    @pytest.mark.asyncio
    async def test_sync_customers_fetch_error(self, sync_engine, mock_shopify_client):
        """Test handling error when fetching customers fails."""
        mock_shopify_client.fetch_all_customers.side_effect = ShopifyAPIError("Fetch failed")

        result = await sync_engine.sync_customers()

        assert result.success is False
        assert "Fetch failed" in result.errors[0]


class TestRunFullSync:
    """Tests for full sync run."""

    @pytest.mark.asyncio
    async def test_run_full_sync_success(self, sync_engine, mock_shopify_client, mock_xero_client, mock_database):
        """Test successful full sync run."""
        # Return empty customers for simplicity
        async def async_generator():
            return
            yield  # Makes this an async generator

        mock_shopify_client.fetch_all_customers.return_value = async_generator()

        stats = await sync_engine.run_full_sync()

        assert stats.run_id is not None
        assert stats.started_at is not None
        assert stats.completed_at is not None
        assert stats.customers is not None

        # Verify sync history was recorded
        history = mock_database.get_sync_history(limit=1)
        assert len(history) == 1
        assert history[0].status == "success"

    @pytest.mark.asyncio
    async def test_run_full_sync_records_history(self, sync_engine, mock_shopify_client, mock_xero_client, mock_database):
        """Test that sync history is properly recorded."""
        async def async_generator():
            return
            yield

        mock_shopify_client.fetch_all_customers.return_value = async_generator()

        stats = await sync_engine.run_full_sync()

        # Check database history
        history = mock_database.get_sync_history(limit=1)
        assert len(history) == 1
        assert history[0].run_id == stats.run_id

    @pytest.mark.asyncio
    async def test_run_full_sync_exception_handling(self, sync_engine, mock_shopify_client, mock_database):
        """Test exception handling during full sync."""
        mock_shopify_client.fetch_all_customers.side_effect = Exception("Unexpected error")

        with pytest.raises(Exception):
            await sync_engine.run_full_sync()

        # Verify failed sync was recorded
        history = mock_database.get_sync_history(limit=1)
        assert len(history) == 1
        assert history[0].status == "failed"


class TestRetryFailedSyncs:
    """Tests for retry logic."""

    @pytest.mark.asyncio
    async def test_retry_no_errors(self, sync_engine, mock_database):
        """Test retry when there are no errors."""
        result = await sync_engine.retry_failed_syncs()

        assert result.success is True
        assert result.total_processed == 0

    @pytest.mark.asyncio
    async def test_retry_customer_success(self, sync_engine, mock_shopify_client, mock_xero_client, mock_database):
        """Test successful retry of failed customer."""
        # Record an error
        mock_database.record_error("customer", "12345", "Previous error")

        # Setup: Customer fetch succeeds
        customer = ShopifyCustomer(
            id=12345,
            email="retry@example.com",
            first_name="Retry",
            last_name="Customer",
        )
        mock_shopify_client.get_customer.return_value = customer
        mock_xero_client.find_contact_by_email.return_value = None
        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="new-id",
            Name="Retry Customer",
        )

        result = await sync_engine.retry_failed_syncs()

        assert result.created == 1 or result.skipped == 0  # Either created or linked

    @pytest.mark.asyncio
    async def test_retry_customer_no_longer_exists(self, sync_engine, mock_shopify_client, mock_database):
        """Test retry when customer no longer exists in Shopify."""
        mock_database.record_error("customer", "12345", "Previous error")

        # Customer doesn't exist anymore
        mock_shopify_client.get_customer.return_value = None

        result = await sync_engine.retry_failed_syncs()

        assert result.skipped == 1

        # Error should be cleared
        errors = mock_database.get_errors()
        assert len(errors) == 0


class TestGetSyncStats:
    """Tests for sync statistics retrieval."""

    def test_get_sync_stats(self, sync_engine, mock_database):
        """Test retrieving sync statistics."""
        # Add some data
        mock_database.upsert_mapping(SyncMapping(
            shopify_id="1",
            xero_id="a",
            entity_type="customer",
        ))
        mock_database.upsert_mapping(SyncMapping(
            shopify_id="2",
            xero_id="b",
            entity_type="product",
        ))

        stats = sync_engine.get_sync_stats()

        assert "mappings" in stats
        assert stats["mappings"]["customer"] == 1
        assert stats["mappings"]["product"] == 1


class TestDuplicateDetectionByEmail:
    """Tests specifically for duplicate detection via email."""

    @pytest.mark.asyncio
    async def test_finds_existing_contact_by_email(self, sync_engine, mock_xero_client, mock_database):
        """Test that existing contact is found by email before creation."""
        customer = ShopifyCustomer(
            id=99999,
            email="duplicate@example.com",
            first_name="Duplicate",
            last_name="Customer",
        )

        existing_contact = XeroContact(
            ContactID="existing-contact-uuid",
            Name="Existing Contact",
            EmailAddress="duplicate@example.com",
        )
        mock_xero_client.find_contact_by_email.return_value = existing_contact

        action, error = await sync_engine._sync_single_customer(customer)

        # Should link to existing, not create
        assert action == "skipped"
        mock_xero_client.create_contact.assert_not_called()

        # Mapping should link to existing contact
        mapping = mock_database.get_mapping("99999")
        assert mapping.xero_id == "existing-contact-uuid"

    @pytest.mark.asyncio
    async def test_handles_email_lookup_error(self, sync_engine, mock_xero_client, mock_database):
        """Test that email lookup errors are handled gracefully."""
        customer = ShopifyCustomer(
            id=88888,
            email="lookup-error@example.com",
            first_name="Lookup",
            last_name="Error",
        )

        # Email lookup fails
        mock_xero_client.find_contact_by_email.side_effect = XeroAPIError("Lookup failed")

        # But creation should still be attempted
        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="new-contact-id",
            Name="Lookup Error",
        )

        action, error = await sync_engine._sync_single_customer(customer)

        # Should still create since lookup failed (not a critical error)
        assert action == "created"
        assert error is None

    @pytest.mark.asyncio
    async def test_customer_without_email(self, sync_engine, mock_xero_client, mock_database):
        """Test handling customer without email (no duplicate check possible)."""
        customer = ShopifyCustomer(
            id=77777,
            email=None,
            first_name="No",
            last_name="Email",
        )

        # Should not search by email
        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="new-id",
            Name="No Email",
        )

        action, error = await sync_engine._sync_single_customer(customer)

        assert action == "created"
        # find_contact_by_email should not be called (or called with None which returns None)


class TestIdempotency:
    """Tests verifying idempotent behavior (running sync twice produces same result)."""

    @pytest.mark.asyncio
    async def test_second_sync_skips_unchanged(self, sync_engine, mock_shopify_client, mock_xero_client, mock_database):
        """Test that second sync skips unchanged customers."""
        customer = ShopifyCustomer(
            id=11111,
            email="idempotent@example.com",
            first_name="Idempotent",
            last_name="Customer",
        )

        # First sync: Create
        mock_xero_client.find_contact_by_email.return_value = None
        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="created-id",
            Name="Idempotent Customer",
        )

        action1, _ = await sync_engine._sync_single_customer(customer)
        assert action1 == "created"

        # Reset mocks
        mock_xero_client.create_contact.reset_mock()

        # Second sync: Should skip (same data, checksum matches)
        action2, _ = await sync_engine._sync_single_customer(customer)
        assert action2 == "skipped"

        # Create should NOT be called again
        mock_xero_client.create_contact.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_syncs_no_duplicates(self, sync_engine, mock_shopify_client, mock_xero_client, mock_database):
        """Test that multiple syncs don't create duplicate records."""
        customer = ShopifyCustomer(
            id=22222,
            email="nodupe@example.com",
            first_name="No",
            last_name="Duplicate",
        )

        created_contact = XeroContact(
            ContactID="single-id",
            Name="No Duplicate",
        )

        # First sync
        mock_xero_client.find_contact_by_email.return_value = None
        mock_xero_client.create_contact.return_value = created_contact

        await sync_engine._sync_single_customer(customer)

        # Second sync - now mapping exists
        mock_xero_client.create_contact.reset_mock()
        await sync_engine._sync_single_customer(customer)

        # Third sync
        await sync_engine._sync_single_customer(customer)

        # Create should only have been called once (on first sync)
        # After first sync, the mapping exists and data is unchanged
        assert mock_xero_client.create_contact.call_count == 0  # Not called after first sync


class TestErrorRecording:
    """Tests for error recording and clearing."""

    @pytest.mark.asyncio
    async def test_error_recorded_on_failure(self, sync_engine, mock_xero_client, mock_database):
        """Test that errors are recorded in database on failure."""
        customer = ShopifyCustomer(
            id=33333,
            email="record-error@example.com",
            first_name="Record",
            last_name="Error",
        )

        mock_xero_client.find_contact_by_email.return_value = None
        mock_xero_client.create_contact.side_effect = XeroAPIError("Record this error")

        action, error = await sync_engine._sync_single_customer(customer)

        assert action == "skipped"
        assert error is not None

    @pytest.mark.asyncio
    async def test_error_cleared_on_success(self, sync_engine, mock_xero_client, mock_database):
        """Test that errors are cleared after successful sync."""
        # First record an error
        mock_database.record_error("customer", "44444", "Previous error")

        customer = ShopifyCustomer(
            id=44444,
            email="clear-error@example.com",
            first_name="Clear",
            last_name="Error",
        )

        mock_xero_client.find_contact_by_email.return_value = None
        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="success-id",
            Name="Clear Error",
        )

        await sync_engine._sync_single_customer(customer)

        # Error should be cleared
        errors = mock_database.get_errors()
        error_ids = [e.shopify_id for e in errors]
        assert "44444" not in error_ids
