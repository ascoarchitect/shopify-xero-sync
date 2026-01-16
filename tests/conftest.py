"""Pytest configuration and shared fixtures.

Provides common fixtures for:
- Event loop configuration for async tests
- Temporary database paths
- Mock environment variables
- Sample Shopify and Xero models
- Database and client fixtures
"""

import pytest
import pytest_asyncio
import asyncio
from pathlib import Path
import tempfile
import os
from datetime import datetime
from unittest.mock import AsyncMock


# =============================================================================
# EVENT LOOP CONFIGURATION
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# TEMPORARY PATHS
# =============================================================================

@pytest.fixture
def temp_db_path():
    """Create a temporary database path for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_sync.db"


@pytest.fixture
def temp_log_path():
    """Create a temporary log file path for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.log"


# =============================================================================
# ENVIRONMENT VARIABLES
# =============================================================================

@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up mock environment variables for testing.

    This provides a complete set of environment variables needed
    for the Settings class to initialize successfully.
    """
    monkeypatch.setenv("SHOPIFY_SHOP_URL", "https://test-store.myshopify.com")
    monkeypatch.setenv("SHOPIFY_API_KEY", "test_api_key")
    monkeypatch.setenv("SHOPIFY_API_SECRET", "test_api_secret")
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "shpat_test_token")
    monkeypatch.setenv("XERO_CLIENT_ID", "test_xero_client_id")
    monkeypatch.setenv("XERO_CLIENT_SECRET", "test_xero_client_secret")
    monkeypatch.setenv("XERO_TENANT_ID", "test_tenant_id")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DRY_RUN", "true")


@pytest.fixture
def mock_env_vars_production(monkeypatch):
    """Set up mock environment variables for production-like testing.

    DRY_RUN is set to false to test actual sync behavior.
    """
    monkeypatch.setenv("SHOPIFY_SHOP_URL", "https://test-store.myshopify.com")
    monkeypatch.setenv("SHOPIFY_API_KEY", "test_api_key")
    monkeypatch.setenv("SHOPIFY_API_SECRET", "test_api_secret")
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "shpat_test_token")
    monkeypatch.setenv("XERO_CLIENT_ID", "test_xero_client_id")
    monkeypatch.setenv("XERO_CLIENT_SECRET", "test_xero_client_secret")
    monkeypatch.setenv("XERO_TENANT_ID", "test_tenant_id")
    monkeypatch.setenv("XERO_ACCESS_TOKEN", "test_access_token")
    monkeypatch.setenv("XERO_REFRESH_TOKEN", "test_refresh_token")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("DRY_RUN", "false")


# =============================================================================
# SAMPLE MODELS
# =============================================================================

@pytest.fixture
def sample_shopify_customer():
    """Create a sample Shopify customer for testing."""
    from src.models import ShopifyCustomer, ShopifyAddress

    return ShopifyCustomer(
        id=123456789,
        email="test.customer@example.com",
        first_name="Test",
        last_name="Customer",
        phone="+441234567890",
        created_at=datetime(2024, 1, 15, 10, 30),
        updated_at=datetime(2024, 1, 20, 14, 45),
        default_address=ShopifyAddress(
            id=987654321,
            address1="123 High Street",
            address2="Flat 2",
            city="London",
            province="Greater London",
            province_code="LND",
            country="United Kingdom",
            country_code="GB",
            zip="SW1A 1AA",
            phone="+441234567890",
            default=True,
        ),
        verified_email=True,
    )


@pytest.fixture
def sample_shopify_customer_minimal():
    """Create a minimal Shopify customer (only required fields)."""
    from src.models import ShopifyCustomer

    return ShopifyCustomer(
        id=100000001,
        email="minimal@example.com",
        first_name="Minimal",
        last_name="Customer",
    )


@pytest.fixture
def sample_shopify_customer_no_email():
    """Create a Shopify customer without email."""
    from src.models import ShopifyCustomer

    return ShopifyCustomer(
        id=100000002,
        email=None,
        first_name="No",
        last_name="Email",
    )


@pytest.fixture
def sample_shopify_product():
    """Create a sample Shopify product for testing."""
    from src.models import ShopifyProduct, ShopifyProductVariant

    return ShopifyProduct(
        id=222222222,
        title="Lavender Wax Melt",
        body_html="<p>Beautiful lavender scented wax melt.</p>",
        vendor="Wax Pop",
        product_type="wax melts",
        created_at=datetime(2024, 1, 5, 10, 0),
        updated_at=datetime(2024, 1, 18, 16, 20),
        status="active",
        tags="fragrance, home, lavender",
        variants=[
            ShopifyProductVariant(
                id=333333333,
                product_id=222222222,
                title="Default",
                price="4.99",
                sku="WM-LAV-001",
                inventory_quantity=50,
                taxable=True,
            )
        ],
    )


@pytest.fixture
def sample_shopify_order():
    """Create a sample Shopify order for testing."""
    from src.models import ShopifyOrder, ShopifyLineItem, ShopifyCustomer

    return ShopifyOrder(
        id=444444444,
        order_number=1001,
        name="#1001",
        email="order.customer@example.com",
        created_at=datetime(2024, 1, 25, 12, 0),
        updated_at=datetime(2024, 1, 25, 12, 5),
        currency="GBP",
        total_price="29.97",
        subtotal_price="24.98",
        total_tax="4.99",
        financial_status="paid",
        line_items=[
            ShopifyLineItem(
                id=555555555,
                variant_id=333333333,
                product_id=222222222,
                title="Lavender Wax Melt",
                quantity=2,
                sku="WM-LAV-001",
                price="4.99",
            ),
            ShopifyLineItem(
                id=555555556,
                variant_id=333333334,
                product_id=222222223,
                title="Rose Wax Melt",
                quantity=3,
                sku="WM-ROS-001",
                price="5.00",
            ),
        ],
    )


@pytest.fixture
def sample_xero_contact():
    """Create a sample Xero contact for testing."""
    from src.models import XeroContact, XeroAddress, XeroPhone

    return XeroContact(
        ContactID="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        Name="Test Customer (test.customer@example.com)",
        FirstName="Test",
        LastName="Customer",
        EmailAddress="test.customer@example.com",
        ContactStatus="ACTIVE",
        IsCustomer=True,
        IsSupplier=False,
        Addresses=[
            XeroAddress(
                AddressType="POBOX",
                AddressLine1="123 High Street",
                AddressLine2="Flat 2",
                City="London",
                Region="Greater London",
                PostalCode="SW1A 1AA",
                Country="United Kingdom",
            )
        ],
        Phones=[
            XeroPhone(
                PhoneType="DEFAULT",
                PhoneNumber="+441234567890",
            )
        ],
    )


@pytest.fixture
def sample_xero_item():
    """Create a sample Xero item for testing."""
    from src.models import XeroItem

    return XeroItem(
        ItemID="item-1111-2222-3333-4444",
        Code="WM-LAV-001",
        Name="Lavender Wax Melt",
        Description="Beautiful lavender scented wax melt.",
        IsSold=True,
        IsPurchased=True,
        SalesDetails={
            "UnitPrice": 4.99,
            "AccountCode": "200",
            "TaxType": "OUTPUT2",
        },
    )


@pytest.fixture
def sample_sync_mapping():
    """Create a sample sync mapping for testing."""
    from src.models import SyncMapping

    return SyncMapping(
        shopify_id="123456789",
        xero_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        entity_type="customer",
        last_synced_at=datetime.utcnow(),
        shopify_updated_at=datetime(2024, 1, 20, 14, 45),
        checksum="abc123def456",
    )


# =============================================================================
# DATABASE AND CLIENT FIXTURES
# =============================================================================

@pytest.fixture
def database(temp_db_path):
    """Create a real database instance for testing."""
    from src.database import Database
    return Database(temp_db_path)


@pytest.fixture
def populated_database(database, sample_sync_mapping):
    """Create a database with some initial data."""
    from src.models import SyncMapping

    # Add some mappings
    database.upsert_mapping(sample_sync_mapping)
    database.upsert_mapping(SyncMapping(
        shopify_id="product-1",
        xero_id="xero-item-1",
        entity_type="product",
    ))
    database.upsert_mapping(SyncMapping(
        shopify_id="order-1",
        xero_id="xero-invoice-1",
        entity_type="order",
    ))

    # Add some sync history
    database.start_sync_run("test-run-1")
    database.complete_sync_run("test-run-1", "success", 3, [])

    return database


# =============================================================================
# MOCK CLIENT FIXTURES
# =============================================================================

@pytest.fixture
def mock_shopify_client_factory(mock_env_vars):
    """Factory for creating mock Shopify clients."""
    from src.shopify_client import ShopifyClient
    from src.config import Settings

    def create_mock():
        settings = Settings()
        client = AsyncMock(spec=ShopifyClient)
        client.settings = settings
        return client

    return create_mock


@pytest.fixture
def mock_xero_client_factory(mock_env_vars):
    """Factory for creating mock Xero clients."""
    from src.xero_client import XeroClient
    from src.config import Settings

    def create_mock():
        settings = Settings()
        client = AsyncMock(spec=XeroClient)
        client.settings = settings
        return client

    return create_mock


# =============================================================================
# UTILITY FIXTURES
# =============================================================================

@pytest.fixture
def assert_no_duplicates():
    """Helper fixture to assert no duplicate mappings exist."""
    def _assert(database, entity_type=None):
        from src.database import Database
        mappings = database.get_all_mappings(entity_type=entity_type)
        shopify_ids = [m.shopify_id for m in mappings]
        xero_ids = [m.xero_id for m in mappings]

        # Check for duplicate Shopify IDs (should be impossible due to PK)
        assert len(shopify_ids) == len(set(shopify_ids)), "Duplicate Shopify IDs found"

        # Note: Xero IDs can be duplicated if multiple Shopify entities
        # map to the same Xero entity (e.g., same email)
        return True

    return _assert


@pytest.fixture
def create_customer_batch():
    """Helper to create a batch of test customers."""
    from src.models import ShopifyCustomer

    def _create(count, start_id=1):
        customers = []
        for i in range(count):
            customers.append(ShopifyCustomer(
                id=start_id + i,
                email=f"customer{start_id + i}@example.com",
                first_name=f"Customer{start_id + i}",
                last_name="Test",
            ))
        return customers

    return _create


@pytest.fixture
def async_customer_generator():
    """Helper to create an async generator from a customer list."""
    async def _generator(customers):
        for customer in customers:
            yield customer

    return _generator
