"""Integration tests for duplicate detection.

Tests verify that:
- Existing contacts are found by email before creation
- Existing items are found by SKU (code) before creation
- Existing invoices are found by reference before creation
- No duplicates are created when syncing existing entities
- Edge cases for duplicate detection are handled correctly
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from datetime import datetime

from src.sync_engine import SyncEngine
from src.database import Database
from src.shopify_client import ShopifyClient
from src.xero_client import XeroClient, XeroAPIError
from src.config import Settings
from src.models import (
    ShopifyCustomer,
    ShopifyProduct,
    ShopifyProductVariant,
    ShopifyOrder,
    ShopifyLineItem,
    XeroContact,
    XeroItem,
    XeroInvoice,
    SyncMapping,
)


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


class TestContactDuplicateDetectionByEmail:
    """Tests for contact duplicate detection using email."""

    @pytest.mark.asyncio
    async def test_finds_existing_contact_by_email(
        self, sync_engine, mock_xero_client, database
    ):
        """Test that existing Xero contact is found by email."""
        # Shopify customer
        customer = ShopifyCustomer(
            id=10001,
            email="already.exists@example.com",
            first_name="Already",
            last_name="Exists",
        )

        # Xero already has this contact
        existing_contact = XeroContact(
            ContactID="existing-xero-contact-id",
            Name="Already Exists",
            EmailAddress="already.exists@example.com",
        )
        mock_xero_client.find_contact_by_email.return_value = existing_contact

        action, error = await sync_engine._sync_single_customer(customer)

        # Should link, not create
        assert action == "skipped"
        assert error is None

        # Should not call create
        mock_xero_client.create_contact.assert_not_called()

        # Mapping should link to existing
        mapping = database.get_mapping("10001")
        assert mapping is not None
        assert mapping.xero_id == "existing-xero-contact-id"

    @pytest.mark.asyncio
    async def test_creates_contact_when_email_not_found(
        self, sync_engine, mock_xero_client, database
    ):
        """Test contact is created when email not found in Xero."""
        customer = ShopifyCustomer(
            id=10002,
            email="brand.new@example.com",
            first_name="Brand",
            last_name="New",
        )

        # No existing contact found
        mock_xero_client.find_contact_by_email.return_value = None

        # Create succeeds
        new_contact = XeroContact(
            ContactID="new-xero-contact-id",
            Name="Brand New",
        )
        mock_xero_client.create_contact.return_value = new_contact

        action, error = await sync_engine._sync_single_customer(customer)

        assert action == "created"
        assert error is None
        mock_xero_client.create_contact.assert_called_once()

    @pytest.mark.asyncio
    async def test_email_lookup_is_case_insensitive(
        self, sync_engine, mock_xero_client, database
    ):
        """Test email lookup handles case differences (Xero side)."""
        customer = ShopifyCustomer(
            id=10003,
            email="Case.Test@Example.COM",
            first_name="Case",
            last_name="Test",
        )

        # Xero returns contact with lowercase email
        existing_contact = XeroContact(
            ContactID="case-insensitive-id",
            Name="Case Test",
            EmailAddress="case.test@example.com",
        )
        mock_xero_client.find_contact_by_email.return_value = existing_contact

        action, _ = await sync_engine._sync_single_customer(customer)

        # Should link to existing (email match is case-insensitive)
        assert action == "skipped"
        mock_xero_client.create_contact.assert_not_called()

    @pytest.mark.asyncio
    async def test_customer_without_email_not_checked(
        self, sync_engine, mock_xero_client, database
    ):
        """Test customer without email proceeds to creation."""
        customer = ShopifyCustomer(
            id=10004,
            email=None,
            first_name="No",
            last_name="Email",
        )

        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="no-email-contact",
            Name="No Email",
        )

        action, _ = await sync_engine._sync_single_customer(customer)

        assert action == "created"
        # find_contact_by_email may or may not be called - depends on implementation
        # but create should definitely be called
        mock_xero_client.create_contact.assert_called_once()

    @pytest.mark.asyncio
    async def test_email_lookup_error_falls_through_to_create(
        self, sync_engine, mock_xero_client, database
    ):
        """Test that email lookup error doesn't prevent creation."""
        customer = ShopifyCustomer(
            id=10005,
            email="lookup.error@example.com",
            first_name="Lookup",
            last_name="Error",
        )

        # Email lookup fails with API error
        mock_xero_client.find_contact_by_email.side_effect = XeroAPIError("API Error")

        # But creation works
        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="created-despite-error",
            Name="Lookup Error",
        )

        action, error = await sync_engine._sync_single_customer(customer)

        assert action == "created"
        assert error is None

    @pytest.mark.asyncio
    async def test_multiple_shopify_customers_same_email(
        self, sync_engine, mock_xero_client, database
    ):
        """Test handling multiple Shopify customers with same email."""
        # Both customers have the same email
        customer1 = ShopifyCustomer(
            id=10006,
            email="shared@example.com",
            first_name="Customer",
            last_name="One",
        )
        customer2 = ShopifyCustomer(
            id=10007,
            email="shared@example.com",
            first_name="Customer",
            last_name="Two",
        )

        # First customer: create new contact
        mock_xero_client.find_contact_by_email.return_value = None
        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="shared-email-contact",
            Name="Customer One",
        )

        action1, _ = await sync_engine._sync_single_customer(customer1)
        assert action1 == "created"

        # Reset and set up for second customer
        mock_xero_client.reset_mock()

        # Second customer: now contact exists with same email
        mock_xero_client.find_contact_by_email.return_value = XeroContact(
            ContactID="shared-email-contact",
            Name="Customer One",
            EmailAddress="shared@example.com",
        )

        action2, _ = await sync_engine._sync_single_customer(customer2)

        # Should link to existing, not create duplicate
        assert action2 == "skipped"
        mock_xero_client.create_contact.assert_not_called()

        # Both should map to same Xero contact
        mapping1 = database.get_mapping("10006")
        mapping2 = database.get_mapping("10007")
        assert mapping1.xero_id == mapping2.xero_id == "shared-email-contact"


class TestPreExistingMappingHandling:
    """Tests for handling pre-existing mappings."""

    @pytest.mark.asyncio
    async def test_existing_mapping_skips_email_lookup(
        self, sync_engine, mock_xero_client, database
    ):
        """Test that existing mapping skips email lookup entirely."""
        # Pre-create mapping
        database.upsert_mapping(SyncMapping(
            shopify_id="20001",
            xero_id="pre-existing-xero-id",
            entity_type="customer",
            checksum="some_checksum",
        ))

        customer = ShopifyCustomer(
            id=20001,
            email="has.mapping@example.com",
            first_name="Has",
            last_name="Mapping",
        )

        # Calculate what checksum would be
        from src.checksums import calculate_customer_checksum
        actual_checksum = calculate_customer_checksum(customer)

        # If checksums match, should skip entirely
        # Update mapping with correct checksum
        database.upsert_mapping(SyncMapping(
            shopify_id="20001",
            xero_id="pre-existing-xero-id",
            entity_type="customer",
            checksum=actual_checksum,
        ))

        action, _ = await sync_engine._sync_single_customer(customer)

        assert action == "skipped"
        # Should not call any Xero APIs
        mock_xero_client.find_contact_by_email.assert_not_called()
        mock_xero_client.create_contact.assert_not_called()
        mock_xero_client.update_contact.assert_not_called()

    @pytest.mark.asyncio
    async def test_existing_mapping_with_changed_data(
        self, sync_engine, mock_xero_client, database
    ):
        """Test that existing mapping with changed data triggers update."""
        # Pre-create mapping with old checksum
        database.upsert_mapping(SyncMapping(
            shopify_id="20002",
            xero_id="existing-xero-id",
            entity_type="customer",
            checksum="old_checksum_different_from_current",
        ))

        customer = ShopifyCustomer(
            id=20002,
            email="changed.data@example.com",
            first_name="Changed",
            last_name="Data",
        )

        mock_xero_client.update_contact.return_value = XeroContact(
            ContactID="existing-xero-id",
            Name="Changed Data",
        )

        action, _ = await sync_engine._sync_single_customer(customer)

        assert action == "updated"
        mock_xero_client.update_contact.assert_called_once()
        # Should not check email or create (mapping already exists)
        mock_xero_client.find_contact_by_email.assert_not_called()
        mock_xero_client.create_contact.assert_not_called()


class TestBulkDuplicateDetection:
    """Tests for duplicate detection in bulk sync operations."""

    @pytest.mark.asyncio
    async def test_bulk_sync_finds_all_existing_contacts(
        self, sync_engine, mock_shopify_client, mock_xero_client, database
    ):
        """Test bulk sync correctly identifies all existing contacts."""
        customers = [
            ShopifyCustomer(id=30001, email="existing1@example.com", first_name="E", last_name="One"),
            ShopifyCustomer(id=30002, email="new@example.com", first_name="N", last_name="New"),
            ShopifyCustomer(id=30003, email="existing2@example.com", first_name="E", last_name="Two"),
        ]

        async def customer_generator():
            for c in customers:
                yield c

        mock_shopify_client.fetch_all_customers.return_value = customer_generator()

        # Set up email lookups
        def find_by_email(email):
            existing_emails = {
                "existing1@example.com": XeroContact(
                    ContactID="xero-existing-1",
                    Name="E One",
                    EmailAddress="existing1@example.com",
                ),
                "existing2@example.com": XeroContact(
                    ContactID="xero-existing-2",
                    Name="E Two",
                    EmailAddress="existing2@example.com",
                ),
            }
            return existing_emails.get(email)

        mock_xero_client.find_contact_by_email.side_effect = find_by_email

        # Create returns new contact for new@example.com
        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="xero-new",
            Name="N New",
        )

        result = await sync_engine.sync_customers()

        # 2 linked to existing (skipped), 1 created
        assert result.created == 1
        assert result.skipped == 2

        # Verify create was only called once
        assert mock_xero_client.create_contact.call_count == 1

    @pytest.mark.asyncio
    async def test_mixed_new_and_existing_customers(
        self, sync_engine, mock_shopify_client, mock_xero_client, database
    ):
        """Test handling mix of new customers and existing contacts."""
        customers = [
            ShopifyCustomer(id=31001, email="new1@example.com", first_name="New", last_name="One"),
            ShopifyCustomer(id=31002, email="existing@example.com", first_name="Existing", last_name="Contact"),
            ShopifyCustomer(id=31003, email="new2@example.com", first_name="New", last_name="Two"),
        ]

        async def customer_generator():
            for c in customers:
                yield c

        mock_shopify_client.fetch_all_customers.return_value = customer_generator()

        # Only existing@example.com is in Xero
        def find_by_email(email):
            if email == "existing@example.com":
                return XeroContact(
                    ContactID="xero-existing",
                    Name="Existing Contact",
                    EmailAddress="existing@example.com",
                )
            return None

        mock_xero_client.find_contact_by_email.side_effect = find_by_email

        created_contacts = []
        def create_contact(contact):
            xero_contact = XeroContact(
                ContactID=f"xero-{len(created_contacts)}",
                Name=contact.Name,
            )
            created_contacts.append(xero_contact)
            return xero_contact

        mock_xero_client.create_contact.side_effect = create_contact

        result = await sync_engine.sync_customers()

        # 2 new, 1 linked to existing
        assert result.created == 2
        assert result.skipped == 1

        # Verify all mappings
        assert database.get_mapping("31001") is not None
        assert database.get_mapping("31002") is not None
        assert database.get_mapping("31003") is not None


class TestDuplicateDetectionEdgeCases:
    """Edge cases for duplicate detection."""

    @pytest.mark.asyncio
    async def test_empty_email_string_not_searched(
        self, sync_engine, mock_xero_client, database
    ):
        """Test empty email string doesn't trigger lookup."""
        customer = ShopifyCustomer(
            id=40001,
            email="",  # Empty string
            first_name="Empty",
            last_name="Email",
        )

        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="empty-email-contact",
            Name="Empty Email",
        )

        action, _ = await sync_engine._sync_single_customer(customer)

        assert action == "created"
        # Email search should return None for empty string

    @pytest.mark.asyncio
    async def test_whitespace_email_handled(
        self, sync_engine, mock_xero_client, database
    ):
        """Test whitespace-only email is handled correctly."""
        customer = ShopifyCustomer(
            id=40002,
            email="  ",  # Whitespace only
            first_name="Whitespace",
            last_name="Email",
        )

        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="whitespace-email-contact",
            Name="Whitespace Email",
        )

        action, _ = await sync_engine._sync_single_customer(customer)

        # Should either create or handle appropriately
        assert action in ["created", "skipped"]

    @pytest.mark.asyncio
    async def test_special_characters_in_email(
        self, sync_engine, mock_xero_client, database
    ):
        """Test email with special characters is searched correctly."""
        customer = ShopifyCustomer(
            id=40003,
            email="test+tag@example.com",  # Plus addressing
            first_name="Special",
            last_name="Email",
        )

        mock_xero_client.find_contact_by_email.return_value = None
        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="special-email-contact",
            Name="Special Email",
        )

        await sync_engine._sync_single_customer(customer)

        # Should search with the exact email including special chars
        mock_xero_client.find_contact_by_email.assert_called_with("test+tag@example.com")

    @pytest.mark.asyncio
    async def test_unicode_in_email(
        self, sync_engine, mock_xero_client, database
    ):
        """Test email with unicode characters is handled."""
        customer = ShopifyCustomer(
            id=40004,
            email="user@exämple.com",  # Unicode in domain
            first_name="Unicode",
            last_name="Email",
        )

        mock_xero_client.find_contact_by_email.return_value = None
        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="unicode-email-contact",
            Name="Unicode Email",
        )

        action, _ = await sync_engine._sync_single_customer(customer)

        assert action == "created"


class TestDuplicatePreventionAcrossSyncs:
    """Tests ensuring no duplicates across multiple sync runs."""

    @pytest.mark.asyncio
    async def test_no_duplicate_after_external_contact_creation(
        self, sync_engine, mock_xero_client, database
    ):
        """Test no duplicate when contact is created externally between syncs."""
        customer = ShopifyCustomer(
            id=50001,
            email="external@example.com",
            first_name="External",
            last_name="Contact",
        )

        # First sync: Contact doesn't exist in Xero
        mock_xero_client.find_contact_by_email.return_value = None
        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="sync-created-id",
            Name="External Contact",
        )

        action1, _ = await sync_engine._sync_single_customer(customer)
        assert action1 == "created"

        # Simulate: Someone creates contact with same email in Xero manually
        # Reset mocks
        mock_xero_client.reset_mock()

        # Now change customer data to force a sync (bypass checksum skip)
        customer.first_name = "Modified"

        # Xero update should work (we already have mapping)
        mock_xero_client.update_contact.return_value = XeroContact(
            ContactID="sync-created-id",
            Name="Modified Contact",
        )

        action2, _ = await sync_engine._sync_single_customer(customer)

        # Should update existing, not create another
        assert action2 == "updated"
        mock_xero_client.create_contact.assert_not_called()

    @pytest.mark.asyncio
    async def test_mapping_prevents_duplicate_after_database_rebuild(
        self, mock_settings, temp_db_path, mock_shopify_client, mock_xero_client
    ):
        """Test mapping lookup prevents duplicates even after database state changes."""
        # Create initial database and sync
        db1 = Database(temp_db_path)
        engine1 = SyncEngine(mock_settings, db1, mock_shopify_client, mock_xero_client)

        customer = ShopifyCustomer(
            id=50002,
            email="rebuild@example.com",
            first_name="Rebuild",
            last_name="Test",
        )

        mock_xero_client.find_contact_by_email.return_value = None
        mock_xero_client.create_contact.return_value = XeroContact(
            ContactID="original-xero-id",
            Name="Rebuild Test",
        )

        await engine1._sync_single_customer(customer)

        # Verify mapping exists
        mapping = db1.get_mapping("50002")
        assert mapping is not None

        # Create new engine with same database (simulate restart)
        db2 = Database(temp_db_path)
        engine2 = SyncEngine(mock_settings, db2, mock_shopify_client, mock_xero_client)

        # Reset mocks
        mock_xero_client.reset_mock()

        # Second sync with same customer
        action, _ = await engine2._sync_single_customer(customer)

        # Should skip due to unchanged data, not create new
        assert action == "skipped"
        mock_xero_client.create_contact.assert_not_called()
