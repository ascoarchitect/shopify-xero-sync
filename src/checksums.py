"""Checksum calculation for change detection.

Checksums are calculated from key fields to detect changes efficiently
without comparing every field or fetching full Xero entities.
"""

import hashlib
from typing import Optional

from .models import ShopifyCustomer, ShopifyProduct, ShopifyOrder


def calculate_customer_checksum(customer: ShopifyCustomer) -> str:
    """Calculate checksum for a Shopify customer.

    Includes fields that matter for the Xero contact:
    - Email (primary identifier)
    - First name, last name
    - Phone number
    - Primary address

    Args:
        customer: Shopify customer entity

    Returns:
        SHA256 hex digest of the relevant fields
    """
    # Get address components safely
    address_parts = []
    if customer.default_address:
        addr = customer.default_address
        address_parts = [
            addr.address1 or "",
            addr.address2 or "",
            addr.city or "",
            addr.province or "",
            addr.zip or "",
            addr.country or "",
        ]

    # Get phone from customer or default address
    phone = customer.phone or ""
    if not phone and customer.default_address:
        phone = customer.default_address.phone or ""

    # Build checksum data string with pipe separator
    data = "|".join([
        customer.email or "",
        customer.first_name or "",
        customer.last_name or "",
        phone,
        *address_parts,
    ])

    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def calculate_product_checksum(product: ShopifyProduct) -> str:
    """Calculate checksum for a Shopify product.

    Includes fields that matter for the Xero item:
    - Title (name in Xero)
    - Vendor
    - Product type
    - Primary variant price
    - Primary variant SKU

    Args:
        product: Shopify product entity

    Returns:
        SHA256 hex digest of the relevant fields
    """
    variant = product.primary_variant

    # Build checksum data string with pipe separator
    data = "|".join([
        product.title or "",
        product.vendor or "",
        product.product_type or "",
        variant.price if variant else "",
        variant.sku or "" if variant else "",
    ])

    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def calculate_order_checksum(order: ShopifyOrder) -> str:
    """Calculate checksum for a Shopify order.

    Includes fields that matter for the Xero invoice:
    - Order number (reference)
    - Total price
    - Line items (titles, quantities, prices)
    - Financial status
    - Customer email

    Args:
        order: Shopify order entity

    Returns:
        SHA256 hex digest of the relevant fields
    """
    # Build line item summary
    line_items_data = []
    for item in order.line_items:
        line_items_data.append(f"{item.title}:{item.quantity}:{item.price}")

    # Build checksum data string with pipe separator
    data = "|".join([
        str(order.order_number),
        order.total_price or "0.00",
        order.subtotal_price or "0.00",
        order.total_tax or "0.00",
        order.financial_status or "",
        order.email or "",
        ";".join(line_items_data),  # Line items separated by semicolon
    ])

    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def has_changed(old_checksum: Optional[str], new_checksum: str) -> bool:
    """Check if an entity has changed based on checksums.

    Args:
        old_checksum: Previous checksum (None if new entity)
        new_checksum: Current checksum

    Returns:
        True if entity has changed or is new
    """
    if old_checksum is None:
        return True
    return old_checksum != new_checksum
