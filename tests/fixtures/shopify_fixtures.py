"""Mock fixtures for Shopify API responses.

These fixtures provide realistic mock data for testing Shopify API operations.
"""

from datetime import datetime, timezone


# =============================================================================
# SHOPIFY CUSTOMER FIXTURES
# =============================================================================

def make_shopify_customer(
    id: int = 123456789,
    email: str = "jane.doe@example.com",
    first_name: str = "Jane",
    last_name: str = "Doe",
    phone: str = "+441onal234567",
    with_address: bool = True,
    **kwargs
) -> dict:
    """Create a mock Shopify customer response.

    Args:
        id: Customer ID
        email: Customer email
        first_name: First name
        last_name: Last name
        phone: Phone number
        with_address: Whether to include a default address
        **kwargs: Additional fields to override

    Returns:
        Dictionary representing Shopify customer API response
    """
    customer = {
        "id": id,
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone,
        "created_at": "2024-01-15T10:30:00Z",
        "updated_at": "2024-01-20T14:45:00Z",
        "note": None,
        "tags": "",
        "tax_exempt": False,
        "verified_email": True,
        "addresses": [],
        "default_address": None,
    }

    if with_address:
        address = {
            "id": 987654321,
            "address1": "123 High Street",
            "address2": "Flat 2",
            "city": "London",
            "province": "Greater London",
            "province_code": "LDN",
            "country": "United Kingdom",
            "country_code": "GB",
            "zip": "SW1A 1AA",
            "phone": phone,
            "company": None,
            "default": True,
        }
        customer["default_address"] = address
        customer["addresses"] = [address]

    customer.update(kwargs)
    return customer


def make_shopify_customers_response(customers: list = None) -> dict:
    """Create a mock Shopify customers list API response.

    Args:
        customers: List of customer dicts. If None, creates a default list.

    Returns:
        Dictionary representing Shopify customers endpoint response
    """
    if customers is None:
        customers = [
            make_shopify_customer(id=1, email="customer1@example.com", first_name="John", last_name="Smith"),
            make_shopify_customer(id=2, email="customer2@example.com", first_name="Jane", last_name="Doe"),
            make_shopify_customer(id=3, email="customer3@example.com", first_name="Bob", last_name="Wilson"),
        ]
    return {"customers": customers}


SHOPIFY_CUSTOMER_MINIMAL = make_shopify_customer(
    id=100,
    email="minimal@example.com",
    first_name="Minimal",
    last_name="Customer",
    phone=None,
    with_address=False,
)

SHOPIFY_CUSTOMER_FULL = make_shopify_customer(
    id=200,
    email="full@example.com",
    first_name="Full",
    last_name="Customer",
    phone="+447700900000",
    with_address=True,
    note="VIP Customer",
    tags="vip, wholesale",
)

SHOPIFY_CUSTOMER_NO_EMAIL = make_shopify_customer(
    id=300,
    email=None,
    first_name="No",
    last_name="Email",
    with_address=True,
)


# =============================================================================
# SHOPIFY PRODUCT FIXTURES
# =============================================================================

def make_shopify_variant(
    id: int = 111111,
    product_id: int = 222222,
    title: str = "Default",
    price: str = "9.99",
    sku: str = "SKU-001",
    inventory_quantity: int = 100,
    **kwargs
) -> dict:
    """Create a mock Shopify product variant."""
    variant = {
        "id": id,
        "product_id": product_id,
        "title": title,
        "price": price,
        "sku": sku,
        "position": 1,
        "inventory_quantity": inventory_quantity,
        "compare_at_price": None,
        "weight": 0.5,
        "weight_unit": "kg",
        "taxable": True,
        "barcode": None,
        "created_at": "2024-01-10T09:00:00Z",
        "updated_at": "2024-01-15T11:30:00Z",
    }
    variant.update(kwargs)
    return variant


def make_shopify_product(
    id: int = 222222,
    title: str = "Lavender Wax Melt",
    product_type: str = "wax melts",
    vendor: str = "Wax Pop",
    sku: str = "WM-LAV-001",
    price: str = "4.99",
    **kwargs
) -> dict:
    """Create a mock Shopify product response.

    Args:
        id: Product ID
        title: Product title
        product_type: Product category
        vendor: Product vendor
        sku: SKU for the default variant
        price: Price for the default variant
        **kwargs: Additional fields to override

    Returns:
        Dictionary representing Shopify product API response
    """
    product = {
        "id": id,
        "title": title,
        "body_html": f"<p>Beautiful {title} for your home.</p>",
        "vendor": vendor,
        "product_type": product_type,
        "created_at": "2024-01-05T10:00:00Z",
        "updated_at": "2024-01-18T16:20:00Z",
        "published_at": "2024-01-05T10:05:00Z",
        "status": "active",
        "tags": "fragrance, home",
        "variants": [
            make_shopify_variant(id=id * 10, product_id=id, sku=sku, price=price)
        ],
    }
    product.update(kwargs)
    return product


def make_shopify_products_response(products: list = None) -> dict:
    """Create a mock Shopify products list API response."""
    if products is None:
        products = [
            make_shopify_product(id=1, title="Lavender Wax Melt", sku="WM-LAV-001"),
            make_shopify_product(id=2, title="Rose Wax Melt", sku="WM-ROS-001"),
            make_shopify_product(id=3, title="Vanilla Candle", product_type="candles", sku="CND-VAN-001"),
        ]
    return {"products": products}


SHOPIFY_PRODUCT_WAX_MELT = make_shopify_product(
    id=1001,
    title="Lavender Dreams Wax Melt",
    product_type="wax melts",
    sku="WM-LAV-DRM-001",
    price="4.99",
)

SHOPIFY_PRODUCT_CANDLE = make_shopify_product(
    id=1002,
    title="Vanilla Bean Candle",
    product_type="candles",
    sku="CND-VAN-BN-001",
    price="12.99",
)

SHOPIFY_PRODUCT_GIFT_SET = make_shopify_product(
    id=1003,
    title="Christmas Gift Set",
    product_type="gift sets",
    sku="GS-XMAS-001",
    price="24.99",
)

SHOPIFY_PRODUCT_NO_SKU = make_shopify_product(
    id=1004,
    title="Mystery Product",
    sku=None,
    variants=[make_shopify_variant(id=10040, product_id=1004, sku=None)],
)


# =============================================================================
# SHOPIFY ORDER FIXTURES
# =============================================================================

def make_shopify_line_item(
    id: int = 333333,
    variant_id: int = 111111,
    product_id: int = 222222,
    title: str = "Lavender Wax Melt",
    quantity: int = 2,
    price: str = "4.99",
    sku: str = "WM-LAV-001",
    **kwargs
) -> dict:
    """Create a mock Shopify order line item."""
    line_item = {
        "id": id,
        "variant_id": variant_id,
        "product_id": product_id,
        "title": title,
        "quantity": quantity,
        "sku": sku,
        "price": price,
        "total_discount": "0.00",
        "tax_lines": [
            {"title": "VAT", "price": str(round(float(price) * quantity * 0.2, 2)), "rate": 0.2}
        ],
    }
    line_item.update(kwargs)
    return line_item


def make_shopify_order(
    id: int = 444444,
    order_number: int = 1001,
    email: str = "customer@example.com",
    total_price: str = "29.97",
    subtotal_price: str = "24.98",
    total_tax: str = "4.99",
    financial_status: str = "paid",
    fulfillment_status: str = None,
    line_items: list = None,
    with_customer: bool = True,
    **kwargs
) -> dict:
    """Create a mock Shopify order response.

    Args:
        id: Order ID
        order_number: Human-readable order number
        email: Customer email
        total_price: Total order price
        subtotal_price: Subtotal before tax
        total_tax: Total tax amount
        financial_status: Payment status
        fulfillment_status: Shipping status
        line_items: List of line item dicts
        with_customer: Whether to include customer data
        **kwargs: Additional fields to override

    Returns:
        Dictionary representing Shopify order API response
    """
    if line_items is None:
        line_items = [
            make_shopify_line_item(id=1, title="Lavender Wax Melt", quantity=2, price="4.99"),
            make_shopify_line_item(id=2, title="Rose Wax Melt", quantity=3, price="5.00"),
        ]

    order = {
        "id": id,
        "order_number": order_number,
        "name": f"#{order_number}",
        "email": email,
        "created_at": "2024-01-25T12:00:00Z",
        "updated_at": "2024-01-25T12:05:00Z",
        "processed_at": "2024-01-25T12:00:00Z",
        "currency": "GBP",
        "total_price": total_price,
        "subtotal_price": subtotal_price,
        "total_tax": total_tax,
        "total_discounts": "0.00",
        "financial_status": financial_status,
        "fulfillment_status": fulfillment_status,
        "customer": make_shopify_customer(email=email) if with_customer else None,
        "line_items": line_items,
        "billing_address": {
            "address1": "123 High Street",
            "city": "London",
            "province": "Greater London",
            "country": "United Kingdom",
            "country_code": "GB",
            "zip": "SW1A 1AA",
        },
        "shipping_address": {
            "address1": "123 High Street",
            "city": "London",
            "province": "Greater London",
            "country": "United Kingdom",
            "country_code": "GB",
            "zip": "SW1A 1AA",
        },
        "note": None,
        "tags": "",
    }
    order.update(kwargs)
    return order


def make_shopify_orders_response(orders: list = None) -> dict:
    """Create a mock Shopify orders list API response."""
    if orders is None:
        orders = [
            make_shopify_order(id=1, order_number=1001, email="order1@example.com"),
            make_shopify_order(id=2, order_number=1002, email="order2@example.com"),
        ]
    return {"orders": orders}


SHOPIFY_ORDER_PAID = make_shopify_order(
    id=2001,
    order_number=1001,
    email="paid@example.com",
    financial_status="paid",
)

SHOPIFY_ORDER_PENDING = make_shopify_order(
    id=2002,
    order_number=1002,
    email="pending@example.com",
    financial_status="pending",
)

SHOPIFY_ORDER_REFUNDED = make_shopify_order(
    id=2003,
    order_number=1003,
    email="refunded@example.com",
    financial_status="refunded",
)


# =============================================================================
# SHOPIFY ERROR RESPONSES
# =============================================================================

SHOPIFY_ERROR_RATE_LIMIT = {
    "errors": "Exceeded 2 calls per second for api client. Reduce request rates to resume uninterrupted service."
}

SHOPIFY_ERROR_AUTH = {
    "errors": "[API] Invalid API key or access token (unrecognized login or wrong password)"
}

SHOPIFY_ERROR_NOT_FOUND = {
    "errors": "Not Found"
}

SHOPIFY_ERROR_INVALID_DATA = {
    "errors": {
        "email": ["is invalid"]
    }
}


# =============================================================================
# SHOPIFY SHOP INFO
# =============================================================================

SHOPIFY_SHOP_INFO = {
    "shop": {
        "id": 12345678,
        "name": "Wax Pop Test Store",
        "email": "admin@waxpop.test",
        "domain": "waxpop.test",
        "province": "Greater London",
        "country": "GB",
        "address1": "123 Test Street",
        "zip": "SW1A 1AA",
        "city": "London",
        "source": None,
        "phone": "+441234567890",
        "latitude": 51.5074,
        "longitude": -0.1278,
        "primary_locale": "en",
        "address2": None,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-15T10:00:00Z",
        "country_code": "GB",
        "country_name": "United Kingdom",
        "currency": "GBP",
        "customer_email": "customers@waxpop.test",
        "timezone": "(GMT+00:00) Europe/London",
        "iana_timezone": "Europe/London",
        "shop_owner": "Adam",
        "money_format": "\u00a3{{amount}}",
        "money_with_currency_format": "\u00a3{{amount}} GBP",
        "weight_unit": "kg",
        "province_code": "LND",
        "taxes_included": True,
        "auto_configure_tax_inclusivity": None,
        "tax_shipping": None,
        "county_taxes": True,
        "plan_display_name": "Development",
        "plan_name": "partner_test",
        "has_discounts": True,
        "has_gift_cards": False,
        "myshopify_domain": "test-store.myshopify.com",
        "google_apps_domain": None,
        "google_apps_login_enabled": None,
        "money_in_emails_format": "\u00a3{{amount}}",
        "money_with_currency_in_emails_format": "\u00a3{{amount}} GBP",
        "eligible_for_payments": True,
        "requires_extra_payments_agreement": False,
        "password_enabled": False,
        "has_storefront": True,
        "finances": True,
        "primary_location_id": 98765432,
        "cookie_consent_level": "implicit",
        "visitor_tracking_consent_preference": "allow_all",
        "checkout_api_supported": True,
        "multi_location_enabled": True,
        "setup_required": False,
        "pre_launch_enabled": False,
        "enabled_presentment_currencies": ["GBP"],
        "transactional_sms_disabled": True,
        "marketing_sms_consent_enabled_at_checkout": False,
    }
}
