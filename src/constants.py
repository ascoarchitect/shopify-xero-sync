"""Constants and mappings for Shopify-Xero sync.

This file contains configuration mappings that may need to be adapted
for specific business requirements, such as product category to GL code mappings.
"""

from typing import NamedTuple


class GLCodeMapping(NamedTuple):
    """GL code mapping for a product category."""
    sales_account: str      # Revenue account code
    purchase_account: str   # Cost of goods sold / expense account code
    description: str        # Human-readable description


# =============================================================================
# PRODUCT CATEGORY TO GL CODE MAPPING
# =============================================================================
# Maps Shopify collection names to Xero account codes.
#
# Xero Account Codes (based on your chart of accounts):
#   Sales Accounts:
#     200 - General Sales (Default)
#     201 - Sales - Essential Oil Collection
#     202 - Sales - Limited Edition Melts
#     203 - Sales - Starter Pack & Gift Boxes
#     204 - Sales - Summer Pops
#     205 - Sales - Wax Burners
#     206 - Sales - Wax Melts
#
#   COGS Accounts:
#     310 - Cost of Goods Sold (General/Default)
#     330 - COGS - Packaging
#     331 - COGS - Oils
#     332 - COGS - Wax
#     333 - COGS - Decorative
#
# NOTE: All products use account 310 (Cost of Goods Sold) as the default COGS
# account during sync. Detailed COGS breakdown (wax, oils, packaging, decorative)
# should be managed within Xero using:
#   - Inventory tracking with component costs
#   - Bills of Materials (BOM) if using Xero Manufacturing/Inventory Plus
#   - Manual journal entries for COGS allocation
#   - Xero Projects for detailed cost tracking
#
# This keeps accounting logic centralized in Xero rather than duplicating it
# in the sync system.
#
# To add a new category:
#   1. Find the Shopify collection name (case-insensitive matching is used)
#   2. Determine the appropriate Xero sales account code
#   3. Add the mapping below (purchase_account will be 310 for all)
#
# =============================================================================

CATEGORY_GL_MAPPING: dict[str, GLCodeMapping] = {
    # Wax Melts - Main product line
    "wax melts": GLCodeMapping(
        sales_account="206",
        purchase_account="310",  # Default COGS - breakdown managed in Xero
        description="Sales - Wax Melts"
    ),
    
    # Essential Oil Collection
    "essential oil collection": GLCodeMapping(
        sales_account="201",
        purchase_account="310",  # Default COGS - breakdown managed in Xero
        description="Sales - Essential Oil Collection"
    ),
    
    # Limited Edition Melts
    "limited edition melts": GLCodeMapping(
        sales_account="202",
        purchase_account="310",  # Default COGS - breakdown managed in Xero
        description="Sales - Limited Edition Melts"
    ),
    
    # Starter Pack & Gift Boxes
    "starter pack & gift boxes": GLCodeMapping(
        sales_account="203",
        purchase_account="310",  # Default COGS - breakdown managed in Xero
        description="Sales - Starter Pack & Gift Boxes"
    ),
    "starter packs": GLCodeMapping(
        sales_account="203",
        purchase_account="310",  # Default COGS - breakdown managed in Xero
        description="Sales - Starter Pack & Gift Boxes"
    ),
    "gift boxes": GLCodeMapping(
        sales_account="203",
        purchase_account="310",  # Default COGS - breakdown managed in Xero
        description="Sales - Starter Pack & Gift Boxes"
    ),
    
    # Summer Pops
    "summer pops": GLCodeMapping(
        sales_account="204",
        purchase_account="310",  # Default COGS - breakdown managed in Xero
        description="Sales - Summer Pops"
    ),
    
    # Wax Burners
    "wax burners": GLCodeMapping(
        sales_account="205",
        purchase_account="310",  # Default COGS - breakdown managed in Xero
        description="Sales - Wax Burners"
    ),
    "burners": GLCodeMapping(
        sales_account="205",
        purchase_account="310",  # Default COGS - breakdown managed in Xero
        description="Sales - Wax Burners"
    ),
}

# Default GL codes for unmapped categories
DEFAULT_GL_MAPPING = GLCodeMapping(
    sales_account="200",      # General Sales (Default)
    purchase_account="310",   # Cost of Goods Sold (Default)
    description="General Sales"
)


def get_gl_codes_for_category(category: str | None) -> GLCodeMapping:
    """Get GL codes for a Shopify product category.

    Performs case-insensitive matching against the category mapping.
    Returns default codes if category is not found or is None.

    Args:
        category: Shopify product_type value (category name)

    Returns:
        GLCodeMapping with sales and purchase account codes

    Example:
        >>> codes = get_gl_codes_for_category("Wax Melts")
        >>> codes.sales_account
        '200'
        >>> codes.purchase_account
        '310'
    """
    if not category:
        return DEFAULT_GL_MAPPING

    # Case-insensitive lookup
    category_lower = category.lower().strip()

    if category_lower in CATEGORY_GL_MAPPING:
        return CATEGORY_GL_MAPPING[category_lower]

    return DEFAULT_GL_MAPPING


# =============================================================================
# TAX TYPES
# =============================================================================
# Xero tax types for UK VAT (adjust for your tax jurisdiction)

TAX_TYPE_STANDARD = "OUTPUT2"      # 20% VAT (standard rate) - for sales/revenue
TAX_TYPE_REDUCED = "RROUTPUT"      # 5% VAT (reduced rate) - for sales/revenue
TAX_TYPE_ZERO = "ZERORATEDOUTPUT"  # 0% VAT (zero rated) - for sales/revenue
TAX_TYPE_EXEMPT = "EXEMPTOUTPUT"   # VAT exempt - for sales/revenue
TAX_TYPE_NO_VAT = "NONE"           # No VAT (not VAT registered)

# Tax types for purchases/expenses
TAX_TYPE_PURCHASE_STANDARD = "INPUT2"      # 20% VAT on purchases
TAX_TYPE_PURCHASE_REDUCED = "RRINPUT"      # 5% VAT on purchases

# Default tax type for product sales
DEFAULT_TAX_TYPE = TAX_TYPE_STANDARD

# Default tax type for product purchases
DEFAULT_PURCHASE_TAX_TYPE = TAX_TYPE_PURCHASE_STANDARD


# =============================================================================
# INVOICE SETTINGS
# =============================================================================

# Default payment terms (days)
DEFAULT_PAYMENT_TERMS_DAYS = 0  # Due immediately for retail

# Invoice reference prefix (prepended to Shopify order number)
INVOICE_REFERENCE_PREFIX = "SHOP-"

# Invoice line item account code (for generic line items)
DEFAULT_LINE_ITEM_ACCOUNT = "200"
