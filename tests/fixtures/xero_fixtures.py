"""Mock fixtures for Xero API responses.

These fixtures provide realistic mock data for testing Xero API operations.
"""

from datetime import datetime
import uuid


# =============================================================================
# XERO CONTACT FIXTURES
# =============================================================================

def make_xero_contact(
    contact_id: str = None,
    name: str = "Jane Doe (jane.doe@example.com)",
    first_name: str = "Jane",
    last_name: str = "Doe",
    email: str = "jane.doe@example.com",
    is_customer: bool = True,
    with_address: bool = True,
    with_phone: bool = True,
    **kwargs
) -> dict:
    """Create a mock Xero contact response.

    Args:
        contact_id: Contact UUID (generated if not provided)
        name: Contact name
        first_name: First name
        last_name: Last name
        email: Email address
        is_customer: Whether contact is a customer
        with_address: Whether to include an address
        with_phone: Whether to include a phone number
        **kwargs: Additional fields to override

    Returns:
        Dictionary representing Xero contact API response
    """
    if contact_id is None:
        contact_id = str(uuid.uuid4())

    contact = {
        "ContactID": contact_id,
        "ContactNumber": None,
        "ContactStatus": "ACTIVE",
        "Name": name,
        "FirstName": first_name,
        "LastName": last_name,
        "EmailAddress": email,
        "Addresses": [],
        "Phones": [],
        "IsCustomer": is_customer,
        "IsSupplier": False,
        "UpdatedDateUTC": "/Date(1705764000000)/",
    }

    if with_address:
        contact["Addresses"] = [
            {
                "AddressType": "POBOX",
                "AddressLine1": "123 High Street",
                "AddressLine2": "Flat 2",
                "City": "London",
                "Region": "Greater London",
                "PostalCode": "SW1A 1AA",
                "Country": "United Kingdom",
            }
        ]

    if with_phone:
        contact["Phones"] = [
            {
                "PhoneType": "DEFAULT",
                "PhoneNumber": "+441234567890",
                "PhoneAreaCode": None,
                "PhoneCountryCode": None,
            }
        ]

    contact.update(kwargs)
    return contact


def make_xero_contacts_response(contacts: list = None) -> dict:
    """Create a mock Xero contacts list API response."""
    if contacts is None:
        contacts = [
            make_xero_contact(name="John Smith", email="john@example.com"),
            make_xero_contact(name="Jane Doe", email="jane@example.com"),
        ]
    return {"Contacts": contacts}


XERO_CONTACT_EXISTING = make_xero_contact(
    contact_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    name="Existing Customer (existing@example.com)",
    email="existing@example.com",
)

XERO_CONTACT_NEW = make_xero_contact(
    contact_id="new11111-2222-3333-4444-555555555555",
    name="New Customer",
    email="new@example.com",
)


# =============================================================================
# XERO ITEM FIXTURES
# =============================================================================

def make_xero_item(
    item_id: str = None,
    code: str = "WM-LAV-001",
    name: str = "Lavender Wax Melt",
    description: str = "Beautiful lavender scented wax melt",
    unit_price: float = 4.99,
    **kwargs
) -> dict:
    """Create a mock Xero item response.

    Args:
        item_id: Item UUID (generated if not provided)
        code: Item code (SKU)
        name: Item name
        description: Item description
        unit_price: Sales unit price
        **kwargs: Additional fields to override

    Returns:
        Dictionary representing Xero item API response
    """
    if item_id is None:
        item_id = str(uuid.uuid4())

    item = {
        "ItemID": item_id,
        "Code": code,
        "Name": name,
        "Description": description,
        "PurchaseDescription": None,
        "PurchaseDetails": {
            "AccountCode": "310",
            "TaxType": "OUTPUT2",
        },
        "SalesDetails": {
            "UnitPrice": unit_price,
            "AccountCode": "200",
            "TaxType": "OUTPUT2",
        },
        "IsTrackedAsInventory": False,
        "IsSold": True,
        "IsPurchased": True,
        "UpdatedDateUTC": "/Date(1705764000000)/",
    }
    item.update(kwargs)
    return item


def make_xero_items_response(items: list = None) -> dict:
    """Create a mock Xero items list API response."""
    if items is None:
        items = [
            make_xero_item(code="WM-LAV-001", name="Lavender Wax Melt"),
            make_xero_item(code="WM-ROS-001", name="Rose Wax Melt"),
            make_xero_item(code="CND-VAN-001", name="Vanilla Candle", unit_price=12.99),
        ]
    return {"Items": items}


XERO_ITEM_WAX_MELT = make_xero_item(
    item_id="item1111-2222-3333-4444-555555555555",
    code="WM-LAV-001",
    name="Lavender Wax Melt",
    unit_price=4.99,
)

XERO_ITEM_CANDLE = make_xero_item(
    item_id="item2222-3333-4444-5555-666666666666",
    code="CND-VAN-001",
    name="Vanilla Candle",
    unit_price=12.99,
)


# =============================================================================
# XERO INVOICE FIXTURES
# =============================================================================

def make_xero_line_item(
    description: str = "Lavender Wax Melt",
    quantity: float = 2.0,
    unit_amount: float = 4.99,
    account_code: str = "200",
    item_code: str = "WM-LAV-001",
    tax_type: str = "OUTPUT2",
    **kwargs
) -> dict:
    """Create a mock Xero invoice line item."""
    line_item = {
        "Description": description,
        "Quantity": quantity,
        "UnitAmount": unit_amount,
        "AccountCode": account_code,
        "ItemCode": item_code,
        "TaxType": tax_type,
        "LineAmount": round(quantity * unit_amount, 2),
    }
    line_item.update(kwargs)
    return line_item


def make_xero_invoice(
    invoice_id: str = None,
    invoice_number: str = "INV-0001",
    reference: str = "SHOP-1001",
    contact_id: str = None,
    status: str = "AUTHORISED",
    line_items: list = None,
    total: float = 29.97,
    subtotal: float = 24.98,
    total_tax: float = 4.99,
    **kwargs
) -> dict:
    """Create a mock Xero invoice response.

    Args:
        invoice_id: Invoice UUID (generated if not provided)
        invoice_number: Xero invoice number
        reference: Reference (Shopify order number)
        contact_id: Contact UUID
        status: Invoice status
        line_items: List of line item dicts
        total: Total invoice amount
        subtotal: Subtotal before tax
        total_tax: Total tax amount
        **kwargs: Additional fields to override

    Returns:
        Dictionary representing Xero invoice API response
    """
    if invoice_id is None:
        invoice_id = str(uuid.uuid4())
    if contact_id is None:
        contact_id = str(uuid.uuid4())
    if line_items is None:
        line_items = [
            make_xero_line_item(description="Lavender Wax Melt", quantity=2, unit_amount=4.99),
            make_xero_line_item(description="Rose Wax Melt", quantity=3, unit_amount=5.00),
        ]

    invoice = {
        "InvoiceID": invoice_id,
        "InvoiceNumber": invoice_number,
        "Reference": reference,
        "Type": "ACCREC",
        "Status": status,
        "Contact": {
            "ContactID": contact_id,
        },
        "LineItems": line_items,
        "Date": "/Date(1706140800000)/",
        "DueDate": "/Date(1706140800000)/",
        "CurrencyCode": "GBP",
        "SubTotal": subtotal,
        "TotalTax": total_tax,
        "Total": total,
        "UpdatedDateUTC": "/Date(1706140800000)/",
    }
    invoice.update(kwargs)
    return invoice


def make_xero_invoices_response(invoices: list = None) -> dict:
    """Create a mock Xero invoices list API response."""
    if invoices is None:
        invoices = [
            make_xero_invoice(reference="SHOP-1001"),
            make_xero_invoice(reference="SHOP-1002"),
        ]
    return {"Invoices": invoices}


XERO_INVOICE_AUTHORISED = make_xero_invoice(
    invoice_id="inv11111-2222-3333-4444-555555555555",
    reference="SHOP-1001",
    status="AUTHORISED",
)

XERO_INVOICE_DRAFT = make_xero_invoice(
    invoice_id="inv22222-3333-4444-5555-666666666666",
    reference="SHOP-1002",
    status="DRAFT",
)


# =============================================================================
# XERO ORGANISATION FIXTURES
# =============================================================================

XERO_ORGANISATION = {
    "Organisations": [
        {
            "OrganisationID": "org11111-2222-3333-4444-555555555555",
            "Name": "Wax Pop Ltd",
            "LegalName": "Wax Pop Limited",
            "PaysTax": True,
            "Version": "UK",
            "OrganisationType": "COMPANY",
            "BaseCurrency": "GBP",
            "CountryCode": "GB",
            "IsDemoCompany": False,
            "OrganisationStatus": "ACTIVE",
            "FinancialYearEndDay": 31,
            "FinancialYearEndMonth": 12,
            "SalesTaxBasis": "ACCRUALS",
            "SalesTaxPeriod": "QUARTERLY",
            "DefaultSalesTax": "Tax Exclusive",
            "DefaultPurchasesTax": "Tax Exclusive",
            "PeriodLockDate": None,
            "EndOfYearLockDate": None,
            "CreatedDateUTC": "/Date(1704067200000)/",
            "Timezone": "GMTSTANDARDTIME",
            "OrganisationEntityType": "COMPANY",
            "ShortCode": "!ABC12",
            "Class": "DEMO",
            "Edition": "BUSINESS",
            "LineOfBusiness": "Retail",
            "Addresses": [
                {
                    "AddressType": "POBOX",
                    "AddressLine1": "123 Business Street",
                    "City": "London",
                    "Region": "Greater London",
                    "PostalCode": "SW1A 1AA",
                    "Country": "United Kingdom",
                }
            ],
            "Phones": [
                {
                    "PhoneType": "DEFAULT",
                    "PhoneNumber": "020 1234 5678",
                    "PhoneAreaCode": None,
                    "PhoneCountryCode": "44",
                }
            ],
            "ExternalLinks": [],
            "PaymentTerms": {},
        }
    ]
}


# =============================================================================
# XERO ERROR RESPONSES
# =============================================================================

XERO_ERROR_RATE_LIMIT = {
    "Type": "RateLimitException",
    "Message": "Rate limit exceeded",
    "ErrorNumber": 17,
}

XERO_ERROR_AUTH = {
    "Type": "UnauthorizedException",
    "Message": "AuthenticationUnsuccessful",
    "ErrorNumber": 11,
}

XERO_ERROR_FORBIDDEN = {
    "Type": "ForbiddenException",
    "Message": "AuthorizationUnsuccessful",
    "ErrorNumber": 13,
}

XERO_ERROR_NOT_FOUND = {
    "Type": "NotFoundException",
    "Message": "The resource you're looking for cannot be found",
    "ErrorNumber": 4,
}

XERO_ERROR_VALIDATION = {
    "Type": "ValidationException",
    "Message": "A validation exception occurred",
    "ErrorNumber": 10,
    "Elements": [
        {
            "ValidationErrors": [
                {
                    "Message": "Email address must be unique"
                }
            ]
        }
    ],
}

XERO_ERROR_DUPLICATE_CONTACT = {
    "Type": "ValidationException",
    "Message": "A validation exception occurred",
    "ErrorNumber": 10,
    "Elements": [
        {
            "ContactID": None,
            "HasAttachments": False,
            "ValidationErrors": [
                {
                    "Message": "A contact with this name already exists. Please enter a unique name."
                }
            ],
        }
    ],
}


# =============================================================================
# XERO OAUTH TOKEN RESPONSES
# =============================================================================

XERO_TOKEN_RESPONSE = {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.test_access_token",
    "token_type": "Bearer",
    "expires_in": 1800,
    "refresh_token": "test_refresh_token_new",
    "scope": "openid profile email accounting.transactions accounting.contacts offline_access",
}

XERO_TOKEN_ERROR = {
    "error": "invalid_grant",
    "error_description": "The refresh token is invalid or expired.",
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def make_empty_contacts_response() -> dict:
    """Create an empty contacts response (for not-found searches)."""
    return {"Contacts": []}


def make_empty_items_response() -> dict:
    """Create an empty items response (for not-found searches)."""
    return {"Items": []}


def make_empty_invoices_response() -> dict:
    """Create an empty invoices response (for not-found searches)."""
    return {"Invoices": []}
