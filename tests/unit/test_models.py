"""Unit tests for Pydantic data models.

Tests verify that:
- Models validate data correctly
- Required fields are enforced
- Default values are applied
- Conversion helpers work correctly
- Edge cases are handled properly
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from src.models import (
    # Shopify models
    ShopifyAddress,
    ShopifyCustomer,
    ShopifyProductVariant,
    ShopifyProduct,
    ShopifyLineItem,
    ShopifyOrder,
    # Xero models
    XeroAddress,
    XeroPhone,
    XeroContact,
    XeroItem,
    XeroLineItem,
    XeroInvoice,
    # Sync models
    SyncMapping,
    SyncHistoryEntry,
    SyncError,
    # Conversion helpers
    shopify_customer_to_xero_contact,
    shopify_product_to_xero_item,
)


class TestShopifyAddress:
    """Tests for ShopifyAddress model."""

    def test_minimal_address(self):
        """Test address with only optional fields."""
        address = ShopifyAddress()

        assert address.id is None
        assert address.address1 is None
        assert address.default is False

    def test_full_address(self):
        """Test address with all fields populated."""
        address = ShopifyAddress(
            id=123,
            address1="123 High Street",
            address2="Flat 2",
            city="London",
            province="Greater London",
            province_code="LDN",
            country="United Kingdom",
            country_code="GB",
            zip="SW1A 1AA",
            phone="+441234567890",
            company="Wax Pop Ltd",
            default=True,
        )

        assert address.id == 123
        assert address.city == "London"
        assert address.default is True


class TestShopifyCustomer:
    """Tests for ShopifyCustomer model."""

    def test_minimal_customer(self):
        """Test customer with only required fields."""
        customer = ShopifyCustomer(id=123)

        assert customer.id == 123
        assert customer.email is None
        assert customer.addresses == []

    def test_full_customer(self):
        """Test customer with all fields populated."""
        customer = ShopifyCustomer(
            id=123,
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            phone="+441234567890",
            created_at=datetime(2024, 1, 15, 10, 30),
            default_address=ShopifyAddress(address1="123 Street"),
            tags="vip",
            tax_exempt=True,
            verified_email=True,
        )

        assert customer.email == "test@example.com"
        assert customer.tax_exempt is True

    def test_full_name_property(self):
        """Test full_name property."""
        customer = ShopifyCustomer(id=1, first_name="John", last_name="Doe")
        assert customer.full_name == "John Doe"

    def test_full_name_with_first_only(self):
        """Test full_name with only first name."""
        customer = ShopifyCustomer(id=1, first_name="John")
        assert customer.full_name == "John"

    def test_full_name_with_last_only(self):
        """Test full_name with only last name."""
        customer = ShopifyCustomer(id=1, last_name="Doe")
        assert customer.full_name == "Doe"

    def test_full_name_unknown(self):
        """Test full_name when no name provided."""
        customer = ShopifyCustomer(id=1)
        assert customer.full_name == "Unknown"

    def test_id_is_required(self):
        """Test that id is required."""
        with pytest.raises(ValidationError):
            ShopifyCustomer()


class TestShopifyProduct:
    """Tests for ShopifyProduct model."""

    def test_minimal_product(self):
        """Test product with only required fields."""
        product = ShopifyProduct(id=123, title="Test Product")

        assert product.id == 123
        assert product.title == "Test Product"
        assert product.variants == []
        assert product.status == "active"

    def test_full_product(self):
        """Test product with all fields populated."""
        product = ShopifyProduct(
            id=123,
            title="Lavender Wax Melt",
            body_html="<p>Description</p>",
            vendor="Wax Pop",
            product_type="wax melts",
            status="active",
            variants=[
                ShopifyProductVariant(id=456, product_id=123, price="4.99", sku="WM-001")
            ],
        )

        assert product.vendor == "Wax Pop"
        assert len(product.variants) == 1

    def test_primary_variant_property(self):
        """Test primary_variant property."""
        product = ShopifyProduct(
            id=123,
            title="Test",
            variants=[
                ShopifyProductVariant(id=1, product_id=123, price="4.99"),
                ShopifyProductVariant(id=2, product_id=123, price="5.99"),
            ],
        )

        assert product.primary_variant.id == 1
        assert product.primary_variant.price == "4.99"

    def test_primary_variant_none(self):
        """Test primary_variant when no variants."""
        product = ShopifyProduct(id=123, title="Test", variants=[])

        assert product.primary_variant is None


class TestShopifyOrder:
    """Tests for ShopifyOrder model."""

    def test_minimal_order(self):
        """Test order with only required fields."""
        order = ShopifyOrder(id=123, order_number=1001, name="#1001")

        assert order.id == 123
        assert order.order_number == 1001
        assert order.currency == "GBP"
        assert order.line_items == []

    def test_full_order(self):
        """Test order with all fields populated."""
        order = ShopifyOrder(
            id=123,
            order_number=1001,
            name="#1001",
            email="customer@example.com",
            currency="GBP",
            total_price="29.97",
            subtotal_price="24.98",
            total_tax="4.99",
            financial_status="paid",
            line_items=[
                ShopifyLineItem(id=1, title="Product A", quantity=2, price="10.00")
            ],
        )

        assert order.email == "customer@example.com"
        assert order.financial_status == "paid"


class TestXeroContact:
    """Tests for XeroContact model."""

    def test_minimal_contact(self):
        """Test contact with only required fields."""
        contact = XeroContact(Name="Test Contact")

        assert contact.Name == "Test Contact"
        assert contact.ContactStatus == "ACTIVE"
        assert contact.IsCustomer is True
        assert contact.IsSupplier is False

    def test_to_api_dict_minimal(self):
        """Test to_api_dict with minimal fields."""
        contact = XeroContact(Name="Test Contact")

        result = contact.to_api_dict()

        assert result["Name"] == "Test Contact"
        assert result["ContactStatus"] == "ACTIVE"
        assert result["IsCustomer"] is True
        assert "ContactID" not in result
        assert "Addresses" not in result

    def test_to_api_dict_full(self):
        """Test to_api_dict with all fields."""
        contact = XeroContact(
            ContactID="abc-123",
            Name="John Doe",
            FirstName="John",
            LastName="Doe",
            EmailAddress="john@example.com",
            Addresses=[XeroAddress(AddressLine1="123 Street")],
            Phones=[XeroPhone(PhoneNumber="+441234567890")],
        )

        result = contact.to_api_dict()

        assert result["ContactID"] == "abc-123"
        assert result["FirstName"] == "John"
        assert result["EmailAddress"] == "john@example.com"
        assert len(result["Addresses"]) == 1
        assert len(result["Phones"]) == 1


class TestXeroItem:
    """Tests for XeroItem model."""

    def test_minimal_item(self):
        """Test item with only required fields."""
        item = XeroItem(Code="SKU-001", Name="Test Item")

        assert item.Code == "SKU-001"
        assert item.Name == "Test Item"
        assert item.IsSold is True
        assert item.IsPurchased is True

    def test_to_api_dict_minimal(self):
        """Test to_api_dict with minimal fields."""
        item = XeroItem(Code="SKU-001", Name="Test Item")

        result = item.to_api_dict()

        assert result["Code"] == "SKU-001"
        assert result["Name"] == "Test Item"
        assert "ItemID" not in result

    def test_to_api_dict_with_sales_details(self):
        """Test to_api_dict with sales details."""
        item = XeroItem(
            ItemID="item-123",
            Code="SKU-001",
            Name="Test Item",
            Description="A test item",
            SalesDetails={"UnitPrice": 9.99, "AccountCode": "200"},
        )

        result = item.to_api_dict()

        assert result["ItemID"] == "item-123"
        assert result["Description"] == "A test item"
        assert result["SalesDetails"]["UnitPrice"] == 9.99


class TestXeroInvoice:
    """Tests for XeroInvoice model."""

    def test_minimal_invoice(self):
        """Test invoice with only required fields."""
        invoice = XeroInvoice()

        assert invoice.Type == "ACCREC"
        assert invoice.Status == "AUTHORISED"
        assert invoice.CurrencyCode == "GBP"

    def test_to_api_dict_minimal(self):
        """Test to_api_dict with minimal fields."""
        invoice = XeroInvoice(
            LineItems=[XeroLineItem(Description="Item", Quantity=1, UnitAmount=10.0)]
        )

        result = invoice.to_api_dict()

        assert result["Type"] == "ACCREC"
        assert result["Status"] == "AUTHORISED"
        assert len(result["LineItems"]) == 1

    def test_to_api_dict_with_date(self):
        """Test to_api_dict formats dates correctly."""
        invoice = XeroInvoice(
            Date=datetime(2024, 1, 25),
            DueDate=datetime(2024, 2, 25),
        )

        result = invoice.to_api_dict()

        assert result["Date"] == "2024-01-25"
        assert result["DueDate"] == "2024-02-25"

    def test_to_api_dict_with_contact(self):
        """Test to_api_dict includes contact reference."""
        invoice = XeroInvoice(ContactID="contact-123")

        result = invoice.to_api_dict()

        assert result["Contact"]["ContactID"] == "contact-123"


class TestSyncModels:
    """Tests for sync-related models."""

    def test_sync_mapping(self):
        """Test SyncMapping model."""
        mapping = SyncMapping(
            shopify_id="123",
            xero_id="abc",
            entity_type="customer",
            last_synced_at=datetime.utcnow(),
            checksum="hash123",
        )

        assert mapping.shopify_id == "123"
        assert mapping.entity_type == "customer"

    def test_sync_history_entry(self):
        """Test SyncHistoryEntry model."""
        entry = SyncHistoryEntry(
            run_id="run-123",
            started_at=datetime.utcnow(),
            status="running",
        )

        assert entry.run_id == "run-123"
        assert entry.entities_processed == 0
        assert entry.errors == []

    def test_sync_error(self):
        """Test SyncError model."""
        error = SyncError(
            entity_type="customer",
            shopify_id="123",
            error_message="API timeout",
            occurred_at=datetime.utcnow(),
        )

        assert error.entity_type == "customer"
        assert error.retry_count == 0


class TestShopifyCustomerToXeroContact:
    """Tests for shopify_customer_to_xero_contact conversion."""

    def test_basic_conversion(self):
        """Test basic customer to contact conversion."""
        customer = ShopifyCustomer(
            id=123,
            email="john@example.com",
            first_name="John",
            last_name="Doe",
        )

        contact = shopify_customer_to_xero_contact(customer)

        assert contact.FirstName == "John"
        assert contact.LastName == "Doe"
        assert contact.EmailAddress == "john@example.com"
        assert contact.IsCustomer is True
        assert contact.IsSupplier is False

    def test_conversion_with_address(self):
        """Test conversion includes address."""
        customer = ShopifyCustomer(
            id=123,
            email="john@example.com",
            first_name="John",
            last_name="Doe",
            default_address=ShopifyAddress(
                address1="123 High Street",
                address2="Flat 2",
                city="London",
                province="Greater London",
                zip="SW1A 1AA",
                country="United Kingdom",
            ),
        )

        contact = shopify_customer_to_xero_contact(customer)

        assert len(contact.Addresses) == 1
        assert contact.Addresses[0].AddressLine1 == "123 High Street"
        assert contact.Addresses[0].City == "London"

    def test_conversion_with_phone(self):
        """Test conversion includes phone."""
        customer = ShopifyCustomer(
            id=123,
            email="john@example.com",
            phone="+441234567890",
        )

        contact = shopify_customer_to_xero_contact(customer)

        assert len(contact.Phones) == 1
        assert contact.Phones[0].PhoneNumber == "+441234567890"

    def test_conversion_phone_from_address(self):
        """Test phone is taken from address if customer phone is None."""
        customer = ShopifyCustomer(
            id=123,
            email="john@example.com",
            phone=None,
            default_address=ShopifyAddress(phone="+449876543210"),
        )

        contact = shopify_customer_to_xero_contact(customer)

        assert len(contact.Phones) == 1
        assert contact.Phones[0].PhoneNumber == "+449876543210"

    def test_conversion_name_with_email(self):
        """Test name includes email for uniqueness."""
        customer = ShopifyCustomer(
            id=123,
            email="john@example.com",
            first_name="John",
            last_name="Doe",
        )

        contact = shopify_customer_to_xero_contact(customer)

        assert "john@example.com" in contact.Name
        assert "John" in contact.Name
        assert "Doe" in contact.Name

    def test_conversion_email_only_name(self):
        """Test name falls back to email when no name provided."""
        customer = ShopifyCustomer(
            id=123,
            email="unknown@example.com",
        )

        contact = shopify_customer_to_xero_contact(customer)

        assert contact.Name == "unknown@example.com"


class TestShopifyProductToXeroItem:
    """Tests for shopify_product_to_xero_item conversion."""

    def test_basic_conversion(self):
        """Test basic product to item conversion."""
        product = ShopifyProduct(
            id=123,
            title="Lavender Wax Melt",
            vendor="Wax Pop",
            product_type="wax melts",
            variants=[
                ShopifyProductVariant(id=456, product_id=123, price="4.99", sku="WM-001")
            ],
        )

        item = shopify_product_to_xero_item(product)

        assert item is not None
        assert item.Code == "WM-001"
        assert item.Name == "Lavender Wax Melt"
        assert item.IsSold is True

    def test_conversion_with_sales_details(self):
        """Test conversion includes sales details with GL codes."""
        product = ShopifyProduct(
            id=123,
            title="Lavender Wax Melt",
            product_type="wax melts",
            variants=[
                ShopifyProductVariant(id=456, product_id=123, price="4.99", sku="WM-001")
            ],
        )

        item = shopify_product_to_xero_item(product)

        assert item.SalesDetails is not None
        assert item.SalesDetails["UnitPrice"] == 4.99
        assert item.SalesDetails["AccountCode"] == "200"

    def test_conversion_without_sku_returns_none(self):
        """Test that products without SKU return None."""
        product = ShopifyProduct(
            id=123,
            title="No SKU Product",
            variants=[
                ShopifyProductVariant(id=456, product_id=123, sku=None)
            ],
        )

        item = shopify_product_to_xero_item(product)

        assert item is None

    def test_conversion_without_variants_returns_none(self):
        """Test that products without variants return None."""
        product = ShopifyProduct(
            id=123,
            title="No Variants",
            variants=[],
        )

        item = shopify_product_to_xero_item(product)

        assert item is None

    def test_conversion_truncates_long_name(self):
        """Test that long product names are truncated to 50 chars."""
        product = ShopifyProduct(
            id=123,
            title="This is a very long product name that exceeds fifty characters limit",
            variants=[
                ShopifyProductVariant(id=456, product_id=123, sku="SKU-001")
            ],
        )

        item = shopify_product_to_xero_item(product)

        assert len(item.Name) == 50

    def test_conversion_with_description(self):
        """Test conversion includes description from body_html."""
        product = ShopifyProduct(
            id=123,
            title="Test Product",
            body_html="<p>Product description here</p>",
            variants=[
                ShopifyProductVariant(id=456, product_id=123, sku="SKU-001")
            ],
        )

        item = shopify_product_to_xero_item(product)

        assert item.Description is not None
        assert "Product description" in item.Description
