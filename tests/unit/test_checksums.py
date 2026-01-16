"""Unit tests for checksum calculation and change detection.

Tests verify that:
- Checksums are calculated consistently from the same data
- Different data produces different checksums
- Change detection works correctly for new and existing entities
- Edge cases (missing fields, None values) are handled correctly
"""

import pytest
import hashlib

from src.checksums import (
    calculate_customer_checksum,
    calculate_product_checksum,
    calculate_order_checksum,
    has_changed,
)
from src.models import (
    ShopifyCustomer,
    ShopifyAddress,
    ShopifyProduct,
    ShopifyProductVariant,
    ShopifyOrder,
    ShopifyLineItem,
)


class TestCalculateCustomerChecksum:
    """Tests for calculate_customer_checksum function."""

    def test_checksum_with_full_customer(self):
        """Test checksum calculation with all fields populated."""
        customer = ShopifyCustomer(
            id=123,
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            phone="+441234567890",
            default_address=ShopifyAddress(
                address1="123 High Street",
                address2="Flat 2",
                city="London",
                province="Greater London",
                zip="SW1A 1AA",
                country="United Kingdom",
            ),
        )

        checksum = calculate_customer_checksum(customer)

        # Should be a 64-character hex string (SHA256)
        assert len(checksum) == 64
        assert checksum.isalnum()

    def test_checksum_is_deterministic(self):
        """Test that same customer produces same checksum."""
        customer = ShopifyCustomer(
            id=123,
            email="test@example.com",
            first_name="John",
            last_name="Doe",
        )

        checksum1 = calculate_customer_checksum(customer)
        checksum2 = calculate_customer_checksum(customer)

        assert checksum1 == checksum2

    def test_different_email_produces_different_checksum(self):
        """Test that different email produces different checksum."""
        customer1 = ShopifyCustomer(
            id=123,
            email="test1@example.com",
            first_name="John",
            last_name="Doe",
        )
        customer2 = ShopifyCustomer(
            id=123,
            email="test2@example.com",
            first_name="John",
            last_name="Doe",
        )

        checksum1 = calculate_customer_checksum(customer1)
        checksum2 = calculate_customer_checksum(customer2)

        assert checksum1 != checksum2

    def test_different_name_produces_different_checksum(self):
        """Test that different name produces different checksum."""
        customer1 = ShopifyCustomer(
            id=123,
            email="test@example.com",
            first_name="John",
            last_name="Doe",
        )
        customer2 = ShopifyCustomer(
            id=123,
            email="test@example.com",
            first_name="Jane",
            last_name="Doe",
        )

        checksum1 = calculate_customer_checksum(customer1)
        checksum2 = calculate_customer_checksum(customer2)

        assert checksum1 != checksum2

    def test_different_address_produces_different_checksum(self):
        """Test that different address produces different checksum."""
        customer1 = ShopifyCustomer(
            id=123,
            email="test@example.com",
            default_address=ShopifyAddress(address1="123 High Street"),
        )
        customer2 = ShopifyCustomer(
            id=123,
            email="test@example.com",
            default_address=ShopifyAddress(address1="456 Low Street"),
        )

        checksum1 = calculate_customer_checksum(customer1)
        checksum2 = calculate_customer_checksum(customer2)

        assert checksum1 != checksum2

    def test_checksum_with_minimal_customer(self):
        """Test checksum with only required fields."""
        customer = ShopifyCustomer(id=123)

        checksum = calculate_customer_checksum(customer)

        assert len(checksum) == 64

    def test_checksum_with_none_email(self):
        """Test checksum handles None email."""
        customer = ShopifyCustomer(
            id=123,
            email=None,
            first_name="John",
            last_name="Doe",
        )

        checksum = calculate_customer_checksum(customer)

        assert len(checksum) == 64

    def test_checksum_phone_from_address_fallback(self):
        """Test that phone is taken from address if customer phone is None."""
        customer_with_address_phone = ShopifyCustomer(
            id=123,
            email="test@example.com",
            phone=None,
            default_address=ShopifyAddress(phone="+441234567890"),
        )
        customer_with_customer_phone = ShopifyCustomer(
            id=123,
            email="test@example.com",
            phone="+441234567890",
            default_address=ShopifyAddress(phone=None),
        )

        # Both should produce the same checksum since they use the same phone
        checksum1 = calculate_customer_checksum(customer_with_address_phone)
        checksum2 = calculate_customer_checksum(customer_with_customer_phone)

        assert checksum1 == checksum2

    def test_checksum_id_not_included(self):
        """Test that ID changes don't affect checksum."""
        customer1 = ShopifyCustomer(
            id=123,
            email="test@example.com",
            first_name="John",
        )
        customer2 = ShopifyCustomer(
            id=456,
            email="test@example.com",
            first_name="John",
        )

        checksum1 = calculate_customer_checksum(customer1)
        checksum2 = calculate_customer_checksum(customer2)

        # ID should not affect checksum - only fields that matter for Xero
        assert checksum1 == checksum2


class TestCalculateProductChecksum:
    """Tests for calculate_product_checksum function."""

    def test_checksum_with_full_product(self):
        """Test checksum calculation with all fields populated."""
        product = ShopifyProduct(
            id=123,
            title="Lavender Wax Melt",
            vendor="Wax Pop",
            product_type="wax melts",
            variants=[
                ShopifyProductVariant(
                    id=456,
                    product_id=123,
                    price="4.99",
                    sku="WM-LAV-001",
                )
            ],
        )

        checksum = calculate_product_checksum(product)

        assert len(checksum) == 64
        assert checksum.isalnum()

    def test_checksum_is_deterministic(self):
        """Test that same product produces same checksum."""
        product = ShopifyProduct(
            id=123,
            title="Lavender Wax Melt",
            variants=[
                ShopifyProductVariant(id=456, product_id=123, price="4.99", sku="WM-001")
            ],
        )

        checksum1 = calculate_product_checksum(product)
        checksum2 = calculate_product_checksum(product)

        assert checksum1 == checksum2

    def test_different_title_produces_different_checksum(self):
        """Test that different title produces different checksum."""
        product1 = ShopifyProduct(
            id=123,
            title="Lavender Wax Melt",
            variants=[ShopifyProductVariant(id=456, product_id=123, sku="WM-001")],
        )
        product2 = ShopifyProduct(
            id=123,
            title="Rose Wax Melt",
            variants=[ShopifyProductVariant(id=456, product_id=123, sku="WM-001")],
        )

        checksum1 = calculate_product_checksum(product1)
        checksum2 = calculate_product_checksum(product2)

        assert checksum1 != checksum2

    def test_different_price_produces_different_checksum(self):
        """Test that different price produces different checksum."""
        product1 = ShopifyProduct(
            id=123,
            title="Lavender Wax Melt",
            variants=[ShopifyProductVariant(id=456, product_id=123, price="4.99", sku="WM-001")],
        )
        product2 = ShopifyProduct(
            id=123,
            title="Lavender Wax Melt",
            variants=[ShopifyProductVariant(id=456, product_id=123, price="5.99", sku="WM-001")],
        )

        checksum1 = calculate_product_checksum(product1)
        checksum2 = calculate_product_checksum(product2)

        assert checksum1 != checksum2

    def test_different_sku_produces_different_checksum(self):
        """Test that different SKU produces different checksum."""
        product1 = ShopifyProduct(
            id=123,
            title="Lavender Wax Melt",
            variants=[ShopifyProductVariant(id=456, product_id=123, sku="WM-001")],
        )
        product2 = ShopifyProduct(
            id=123,
            title="Lavender Wax Melt",
            variants=[ShopifyProductVariant(id=456, product_id=123, sku="WM-002")],
        )

        checksum1 = calculate_product_checksum(product1)
        checksum2 = calculate_product_checksum(product2)

        assert checksum1 != checksum2

    def test_checksum_with_no_variants(self):
        """Test checksum handles product without variants."""
        product = ShopifyProduct(id=123, title="Lavender Wax Melt", variants=[])

        checksum = calculate_product_checksum(product)

        assert len(checksum) == 64

    def test_different_vendor_produces_different_checksum(self):
        """Test that different vendor produces different checksum."""
        product1 = ShopifyProduct(
            id=123,
            title="Lavender Wax Melt",
            vendor="Vendor A",
            variants=[ShopifyProductVariant(id=456, product_id=123, sku="WM-001")],
        )
        product2 = ShopifyProduct(
            id=123,
            title="Lavender Wax Melt",
            vendor="Vendor B",
            variants=[ShopifyProductVariant(id=456, product_id=123, sku="WM-001")],
        )

        checksum1 = calculate_product_checksum(product1)
        checksum2 = calculate_product_checksum(product2)

        assert checksum1 != checksum2


class TestCalculateOrderChecksum:
    """Tests for calculate_order_checksum function."""

    def test_checksum_with_full_order(self):
        """Test checksum calculation with all fields populated."""
        order = ShopifyOrder(
            id=123,
            order_number=1001,
            name="#1001",
            email="customer@example.com",
            total_price="29.97",
            subtotal_price="24.98",
            total_tax="4.99",
            financial_status="paid",
            line_items=[
                ShopifyLineItem(id=1, title="Lavender Wax Melt", quantity=2, price="4.99"),
                ShopifyLineItem(id=2, title="Rose Wax Melt", quantity=3, price="5.00"),
            ],
        )

        checksum = calculate_order_checksum(order)

        assert len(checksum) == 64
        assert checksum.isalnum()

    def test_checksum_is_deterministic(self):
        """Test that same order produces same checksum."""
        order = ShopifyOrder(
            id=123,
            order_number=1001,
            name="#1001",
            total_price="29.97",
            line_items=[
                ShopifyLineItem(id=1, title="Product A", quantity=1, price="10.00"),
            ],
        )

        checksum1 = calculate_order_checksum(order)
        checksum2 = calculate_order_checksum(order)

        assert checksum1 == checksum2

    def test_different_total_produces_different_checksum(self):
        """Test that different total produces different checksum."""
        order1 = ShopifyOrder(
            id=123,
            order_number=1001,
            name="#1001",
            total_price="29.97",
            line_items=[ShopifyLineItem(id=1, title="A", quantity=1, price="10.00")],
        )
        order2 = ShopifyOrder(
            id=123,
            order_number=1001,
            name="#1001",
            total_price="39.97",
            line_items=[ShopifyLineItem(id=1, title="A", quantity=1, price="10.00")],
        )

        checksum1 = calculate_order_checksum(order1)
        checksum2 = calculate_order_checksum(order2)

        assert checksum1 != checksum2

    def test_different_line_items_produce_different_checksum(self):
        """Test that different line items produce different checksum."""
        order1 = ShopifyOrder(
            id=123,
            order_number=1001,
            name="#1001",
            line_items=[ShopifyLineItem(id=1, title="Product A", quantity=1, price="10.00")],
        )
        order2 = ShopifyOrder(
            id=123,
            order_number=1001,
            name="#1001",
            line_items=[ShopifyLineItem(id=1, title="Product B", quantity=1, price="10.00")],
        )

        checksum1 = calculate_order_checksum(order1)
        checksum2 = calculate_order_checksum(order2)

        assert checksum1 != checksum2

    def test_different_quantity_produces_different_checksum(self):
        """Test that different quantity produces different checksum."""
        order1 = ShopifyOrder(
            id=123,
            order_number=1001,
            name="#1001",
            line_items=[ShopifyLineItem(id=1, title="Product A", quantity=1, price="10.00")],
        )
        order2 = ShopifyOrder(
            id=123,
            order_number=1001,
            name="#1001",
            line_items=[ShopifyLineItem(id=1, title="Product A", quantity=5, price="10.00")],
        )

        checksum1 = calculate_order_checksum(order1)
        checksum2 = calculate_order_checksum(order2)

        assert checksum1 != checksum2

    def test_checksum_with_no_line_items(self):
        """Test checksum handles order without line items."""
        order = ShopifyOrder(
            id=123,
            order_number=1001,
            name="#1001",
            line_items=[],
        )

        checksum = calculate_order_checksum(order)

        assert len(checksum) == 64

    def test_different_financial_status_produces_different_checksum(self):
        """Test that different financial status produces different checksum."""
        order1 = ShopifyOrder(
            id=123,
            order_number=1001,
            name="#1001",
            financial_status="paid",
            line_items=[],
        )
        order2 = ShopifyOrder(
            id=123,
            order_number=1001,
            name="#1001",
            financial_status="pending",
            line_items=[],
        )

        checksum1 = calculate_order_checksum(order1)
        checksum2 = calculate_order_checksum(order2)

        assert checksum1 != checksum2


class TestHasChanged:
    """Tests for has_changed function."""

    def test_returns_true_for_none_old_checksum(self):
        """Test that None old checksum indicates new entity (changed)."""
        result = has_changed(None, "abc123")

        assert result is True

    def test_returns_true_for_different_checksums(self):
        """Test that different checksums indicate change."""
        result = has_changed("abc123", "def456")

        assert result is True

    def test_returns_false_for_same_checksums(self):
        """Test that same checksums indicate no change."""
        result = has_changed("abc123", "abc123")

        assert result is False

    def test_returns_true_for_empty_old_checksum(self):
        """Test that empty string old checksum indicates change."""
        result = has_changed("", "abc123")

        assert result is True

    def test_case_sensitive_comparison(self):
        """Test that checksum comparison is case-sensitive."""
        result = has_changed("ABC123", "abc123")

        assert result is True

    def test_handles_long_checksums(self):
        """Test with actual SHA256-length checksums."""
        checksum1 = hashlib.sha256(b"data1").hexdigest()
        checksum2 = hashlib.sha256(b"data2").hexdigest()

        assert has_changed(checksum1, checksum2) is True
        assert has_changed(checksum1, checksum1) is False
