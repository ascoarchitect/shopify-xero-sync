"""Pydantic data models for Shopify and Xero entities.

These models provide validation and type safety for data moving
between Shopify, Xero, and the local SQLite database.
"""

import re
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr, field_validator


def parse_shopify_datetime(value):
    """Parse Shopify datetime strings, handling various formats.
    
    Shopify returns ISO 8601 format like: 2024-01-15T12:30:45+00:00
    This handles the parsing robustly to avoid issues with timezone formats.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            # Try standard ISO format first
            return datetime.fromisoformat(value)
        except (ValueError, AttributeError):
            pass
        
        try:
            # Handle various timezone formats
            # Replace common patterns
            cleaned = value.strip()
            
            # Remove 'Z' suffix and treat as UTC
            if cleaned.endswith('Z'):
                cleaned = cleaned[:-1] + '+00:00'
            
            # Ensure timezone has colon (2024-01-15T12:30:45+0000 -> +00:00)
            import re
            cleaned = re.sub(r'([+-]\d{2})(\d{2})$', r'\1:\2', cleaned)
            
            return datetime.fromisoformat(cleaned)
        except (ValueError, AttributeError) as e:
            # Last resort: parse without timezone
            try:
                # Remove timezone info entirely
                base = value.split('+')[0].split('-')
                # Rejoin date parts (YYYY-MM-DD) but not time
                if 'T' in value:
                    return datetime.fromisoformat(value.split('+')[0].split('Z')[0])
                return None
            except:
                # Give up and return None
                return None
    return value


# =============================================================================
# SHOPIFY MODELS
# =============================================================================

class ShopifyAddress(BaseModel):
    """Shopify customer address."""
    id: Optional[int] = None
    address1: Optional[str] = None
    address2: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    province_code: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    default: bool = False


class ShopifyCustomer(BaseModel):
    """Shopify customer entity."""
    id: int
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    default_address: Optional[ShopifyAddress] = None
    addresses: List[ShopifyAddress] = Field(default_factory=list)
    note: Optional[str] = None
    tags: Optional[str] = None
    tax_exempt: bool = False
    verified_email: bool = False
    email_marketing_consent: Optional[dict] = None  # Contains marketingState, marketingOptInLevel, consentUpdatedAt

    @field_validator('created_at', 'updated_at', mode='before')
    @classmethod
    def parse_datetime(cls, value):
        """Parse datetime fields with custom handler."""
        return parse_shopify_datetime(value)

    @property
    def full_name(self) -> str:
        """Get customer's full name."""
        parts = [self.first_name, self.last_name]
        return " ".join(p for p in parts if p) or "Unknown"

    @property
    def is_subscribed_to_email_marketing(self) -> bool:
        """Check if customer is subscribed to email marketing."""
        if not self.email_marketing_consent:
            return False
        marketing_state = self.email_marketing_consent.get('marketingState', 'NOT_SUBSCRIBED')
        return marketing_state == 'SUBSCRIBED'


class ShopifyProductVariant(BaseModel):
    """Shopify product variant."""
    id: int
    product_id: int
    title: Optional[str] = None
    price: str = "0.00"
    sku: Optional[str] = None
    position: int = 1
    inventory_quantity: int = 0
    compare_at_price: Optional[str] = None
    weight: Optional[float] = None
    weight_unit: str = "kg"
    taxable: bool = True
    barcode: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ShopifyProduct(BaseModel):
    """Shopify product entity."""
    id: int
    title: str
    body_html: Optional[str] = None
    vendor: Optional[str] = None
    product_type: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    status: str = "active"
    tags: Optional[str] = None
    variants: List[ShopifyProductVariant] = Field(default_factory=list)

    @field_validator('created_at', 'updated_at', 'published_at', mode='before')
    @classmethod
    def parse_datetime(cls, value):
        """Parse datetime fields with custom handler."""
        return parse_shopify_datetime(value)

    @property
    def primary_variant(self) -> Optional[ShopifyProductVariant]:
        """Get the first/primary variant."""
        return self.variants[0] if self.variants else None


class ShopifyLineItem(BaseModel):
    """Line item in a Shopify order."""
    id: int
    variant_id: Optional[int] = None
    product_id: Optional[int] = None
    title: str
    quantity: int
    sku: Optional[str] = None
    price: str = "0.00"
    total_discount: str = "0.00"
    tax_lines: List[dict] = Field(default_factory=list)


class ShopifyOrder(BaseModel):
    """Shopify order entity."""
    id: int
    order_number: int
    name: str  # e.g., "#1001"
    email: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    currency: str = "GBP"
    total_price: str = "0.00"
    subtotal_price: str = "0.00"
    total_tax: str = "0.00"
    total_discounts: str = "0.00"
    financial_status: Optional[str] = None
    fulfillment_status: Optional[str] = None
    customer: Optional[ShopifyCustomer] = None
    line_items: List[ShopifyLineItem] = Field(default_factory=list)
    billing_address: Optional[ShopifyAddress] = None
    shipping_address: Optional[ShopifyAddress] = None
    note: Optional[str] = None
    tags: Optional[str] = None

    @field_validator('created_at', 'updated_at', 'processed_at', mode='before')
    @classmethod
    def parse_datetime(cls, value):
        """Parse datetime fields with custom handler."""
        return parse_shopify_datetime(value)


# =============================================================================
# XERO MODELS
# =============================================================================

class XeroAddress(BaseModel):
    """Xero contact address."""
    AddressType: str = "POBOX"  # POBOX, STREET, DELIVERY
    AddressLine1: Optional[str] = None
    AddressLine2: Optional[str] = None
    City: Optional[str] = None
    Region: Optional[str] = None
    PostalCode: Optional[str] = None
    Country: Optional[str] = None


class XeroPhone(BaseModel):
    """Xero contact phone number."""
    PhoneType: str = "DEFAULT"  # DEFAULT, DDI, MOBILE, FAX
    PhoneNumber: Optional[str] = None
    PhoneAreaCode: Optional[str] = None
    PhoneCountryCode: Optional[str] = None


class XeroContact(BaseModel):
    """Xero contact entity (customer/supplier)."""
    ContactID: Optional[str] = None
    ContactNumber: Optional[str] = None
    ContactStatus: str = "ACTIVE"
    Name: str
    FirstName: Optional[str] = None
    LastName: Optional[str] = None
    EmailAddress: Optional[str] = None
    Addresses: List[XeroAddress] = Field(default_factory=list)
    Phones: List[XeroPhone] = Field(default_factory=list)
    IsCustomer: bool = True
    IsSupplier: bool = False
    UpdatedDateUTC: Optional[datetime] = None

    def to_api_dict(self) -> dict:
        """Convert to dict for Xero API submission."""
        data = {
            "Name": self.Name,
            "ContactStatus": self.ContactStatus,
            "IsCustomer": self.IsCustomer,
            "IsSupplier": self.IsSupplier,
        }
        if self.ContactID:
            data["ContactID"] = self.ContactID
        if self.FirstName:
            data["FirstName"] = self.FirstName
        if self.LastName:
            data["LastName"] = self.LastName
        if self.EmailAddress:
            data["EmailAddress"] = self.EmailAddress
        if self.Addresses:
            data["Addresses"] = [addr.model_dump(exclude_none=True) for addr in self.Addresses]
        if self.Phones:
            data["Phones"] = [phone.model_dump(exclude_none=True) for phone in self.Phones]
        return data


class XeroItem(BaseModel):
    """Xero inventory item (product)."""
    ItemID: Optional[str] = None
    Code: str  # SKU - must be unique
    Name: str
    Description: Optional[str] = None
    PurchaseDescription: Optional[str] = None
    PurchaseDetails: Optional[dict] = None
    SalesDetails: Optional[dict] = None
    IsTrackedAsInventory: bool = False
    IsSold: bool = True
    IsPurchased: bool = True
    UpdatedDateUTC: Optional[datetime] = None

    def to_api_dict(self) -> dict:
        """Convert to dict for Xero API submission."""
        data = {
            "Code": self.Code,
            "Name": self.Name,
            "IsSold": self.IsSold,
            "IsPurchased": self.IsPurchased,
        }
        if self.ItemID:
            data["ItemID"] = self.ItemID
        if self.Description:
            data["Description"] = self.Description
        if self.SalesDetails:
            data["SalesDetails"] = self.SalesDetails
        return data


class XeroLineItem(BaseModel):
    """Line item in a Xero invoice.

    AccountCode and TaxType can be customized per line item based on
    product category. See constants.py for GL code mappings.
    """
    Description: str
    Quantity: float = 1.0
    UnitAmount: float
    AccountCode: str = "200"  # Default sales account - override via constants
    ItemCode: Optional[str] = None
    TaxType: str = "OUTPUT2"  # Default UK VAT - see constants.py for options
    LineAmount: Optional[float] = None


class XeroInvoice(BaseModel):
    """Xero invoice entity."""
    InvoiceID: Optional[str] = None
    InvoiceNumber: Optional[str] = None
    Reference: Optional[str] = None  # Shopify order number goes here
    Type: str = "ACCREC"  # ACCREC = Sales invoice
    Status: str = "AUTHORISED"
    Contact: Optional[XeroContact] = None
    ContactID: Optional[str] = None
    LineItems: List[XeroLineItem] = Field(default_factory=list)
    Date: Optional[datetime] = None
    DueDate: Optional[datetime] = None
    CurrencyCode: str = "GBP"
    SubTotal: Optional[float] = None
    TotalTax: Optional[float] = None
    Total: Optional[float] = None
    UpdatedDateUTC: Optional[datetime] = None

    def to_api_dict(self) -> dict:
        """Convert to dict for Xero API submission."""
        data = {
            "Type": self.Type,
            "Status": self.Status,
            "CurrencyCode": self.CurrencyCode,
            "LineItems": [li.model_dump(exclude_none=True) for li in self.LineItems],
        }
        if self.InvoiceID:
            data["InvoiceID"] = self.InvoiceID
        if self.Reference:
            data["Reference"] = self.Reference
        if self.ContactID:
            data["Contact"] = {"ContactID": self.ContactID}
        if self.Date:
            data["Date"] = self.Date.strftime("%Y-%m-%d")
        if self.DueDate:
            data["DueDate"] = self.DueDate.strftime("%Y-%m-%d")
        return data


# =============================================================================
# SYNC MAPPING MODELS
# =============================================================================

class SyncMapping(BaseModel):
    """Mapping between Shopify and Xero entities."""
    shopify_id: str
    xero_id: str
    entity_type: str  # "customer", "product", "order"
    last_synced_at: Optional[datetime] = None
    shopify_updated_at: Optional[datetime] = None
    checksum: Optional[str] = None


class SyncHistoryEntry(BaseModel):
    """Record of a sync run."""
    run_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str  # "running", "success", "failed"
    entities_processed: int = 0
    errors: List[str] = Field(default_factory=list)


class SyncError(BaseModel):
    """Record of a sync error for retry."""
    id: Optional[int] = None
    entity_type: str
    shopify_id: str
    error_message: str
    occurred_at: datetime
    retry_count: int = 0


# =============================================================================
# CONVERSION HELPERS
# =============================================================================

def shopify_customer_to_xero_contact(customer: ShopifyCustomer) -> XeroContact:
    """Convert a Shopify customer to a Xero contact.

    Args:
        customer: Shopify customer data

    Returns:
        XeroContact: Xero contact ready for creation/update
    """
    # Build addresses
    addresses = []
    if customer.default_address:
        addr = customer.default_address
        addresses.append(XeroAddress(
            AddressType="POBOX",
            AddressLine1=addr.address1,
            AddressLine2=addr.address2,
            City=addr.city,
            Region=addr.province,
            PostalCode=addr.zip,
            Country=addr.country,
        ))

    # Build phones
    phones = []
    phone_number = customer.phone or (customer.default_address.phone if customer.default_address else None)
    if phone_number:
        phones.append(XeroPhone(
            PhoneType="DEFAULT",
            PhoneNumber=phone_number,
        ))

    # Determine contact name
    # Xero requires a unique Name field - use full name or email
    name = customer.full_name
    if name == "Unknown" and customer.email:
        name = customer.email
    elif customer.email:
        # Include email in name to help with uniqueness
        name = f"{customer.full_name} ({customer.email})"

    return XeroContact(
        Name=name,
        FirstName=customer.first_name,
        LastName=customer.last_name,
        EmailAddress=customer.email,
        Addresses=addresses,
        Phones=phones,
        IsCustomer=True,
        IsSupplier=False,
    )


def shopify_product_to_xero_item(product: ShopifyProduct) -> Optional[XeroItem]:
    """Convert a Shopify product to a Xero item.

    Uses the product's category (product_type) to determine the appropriate
    GL codes for sales and purchase accounts via the constants mapping.

    Args:
        product: Shopify product data

    Returns:
        XeroItem or None if product has no SKU
    """
    from .constants import get_gl_codes_for_category, DEFAULT_TAX_TYPE, DEFAULT_PURCHASE_TAX_TYPE

    def strip_html(text: Optional[str]) -> Optional[str]:
        """Remove HTML tags and decode entities from text."""
        if not text:
            return None
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Replace common HTML entities
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        text = text.replace('&#39;', "'")
        text = text.replace('&nbsp;', ' ')
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text if text else None

    variant = product.primary_variant
    if not variant or not variant.sku:
        return None  # Can't create Xero item without SKU

    # Get GL codes based on product category
    gl_codes = get_gl_codes_for_category(product.product_type)

    # Build sales details with price and category-specific GL code
    price = float(variant.price) if variant.price else 0.0
    sales_details = {
        "UnitPrice": price,
        "AccountCode": gl_codes.sales_account,
        "TaxType": DEFAULT_TAX_TYPE,  # OUTPUT2 for sales
    }

    # Build purchase details with category-specific GL code
    purchase_details = {
        "AccountCode": gl_codes.purchase_account,
        "TaxType": DEFAULT_PURCHASE_TAX_TYPE,  # INPUT2 for purchases
    }

    return XeroItem(
        Code=variant.sku,
        Name=product.title[:50],  # Xero has 50 char limit on Name
        Description=product.title,  # Use product name as description
        SalesDetails=sales_details,
        PurchaseDetails=purchase_details,
        IsSold=True,
        IsPurchased=True,
    )


def shopify_order_to_xero_invoice(
    order: ShopifyOrder,
    contact_id: str,
    sku_to_gl_code: Optional[dict] = None,
) -> XeroInvoice:
    """Convert a Shopify order to a Xero invoice.

    Args:
        order: Shopify order data
        contact_id: Xero ContactID for the customer
        sku_to_gl_code: Optional mapping of SKU to GL account code

    Returns:
        XeroInvoice ready for creation
    """
    from .constants import (
        DEFAULT_LINE_ITEM_ACCOUNT,
        DEFAULT_TAX_TYPE,
        INVOICE_REFERENCE_PREFIX,
    )
    from datetime import timedelta

    # Build line items from order
    line_items = []
    for item in order.line_items:
        # Determine account code - use SKU mapping if available, else default
        account_code = DEFAULT_LINE_ITEM_ACCOUNT
        if sku_to_gl_code and item.sku:
            account_code = sku_to_gl_code.get(item.sku, DEFAULT_LINE_ITEM_ACCOUNT)

        line_items.append(XeroLineItem(
            Description=item.title,
            Quantity=float(item.quantity),
            UnitAmount=float(item.price) if item.price else 0.0,
            AccountCode=account_code,
            ItemCode=item.sku,  # Link to Xero item if it exists
            TaxType=DEFAULT_TAX_TYPE,
        ))

    # Add discount as negative line item if present
    if order.total_discounts and float(order.total_discounts) > 0:
        line_items.append(XeroLineItem(
            Description="Discount",
            Quantity=1.0,
            UnitAmount=-float(order.total_discounts),
            AccountCode=DEFAULT_LINE_ITEM_ACCOUNT,
            TaxType=DEFAULT_TAX_TYPE,
        ))

    # Build invoice reference from Shopify order number
    reference = f"{INVOICE_REFERENCE_PREFIX}{order.order_number}"

    # Set dates
    invoice_date = order.created_at or datetime.utcnow()
    # Due immediately for retail orders
    due_date = invoice_date

    # Determine invoice status based on payment status
    status = "DRAFT"
    if order.financial_status == "paid":
        status = "AUTHORISED"

    return XeroInvoice(
        Reference=reference,
        Type="ACCREC",  # Accounts Receivable (sales invoice)
        Status=status,
        ContactID=contact_id,
        LineItems=line_items,
        Date=invoice_date,
        DueDate=due_date,
        CurrencyCode=order.currency or "GBP",
    )
