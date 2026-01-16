"""Xero API client using the official xero-python SDK.

Handles OAuth2 authentication with automatic token refresh and persistence,
and provides methods for managing contacts, items, and invoices in Xero.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import List, Optional, Callable, Dict, Any
from datetime import datetime

from xero_python.api_client import ApiClient, Configuration
from xero_python.api_client.oauth2 import OAuth2Token
from xero_python.accounting import (
    AccountingApi,
    Contact,
    Contacts,
    Item,
    Items,
    Invoice,
    Invoices,
    Address,
    Phone,
    LineItem,
)
from xero_python.exceptions import AccountingBadRequestException

from .config import Settings
from .models import XeroContact, XeroItem, XeroInvoice, XeroAddress, XeroPhone, XeroLineItem

logger = logging.getLogger(__name__)


class XeroAPIError(Exception):
    """Base exception for Xero API errors."""
    pass


class XeroRateLimitError(XeroAPIError):
    """Raised when rate limit is exceeded."""
    def __init__(self, retry_after: float = 60.0):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s")


class XeroAuthError(XeroAPIError):
    """Raised when authentication fails."""
    pass


class XeroClient:
    """Client for Xero API using the official SDK.

    Wraps the synchronous SDK calls with asyncio.to_thread() to maintain
    async compatibility with the rest of the codebase.
    """

    # Token storage file path (relative to data directory)
    TOKEN_FILE = "xero_tokens.json"

    def __init__(self, settings: Settings):
        """Initialize Xero client with official SDK.

        Args:
            settings: Application settings with Xero credentials
        """
        self.settings = settings
        self._tenant_id = settings.xero_tenant_id
        self._token_path = settings.database_path.parent / self.TOKEN_FILE

        # SDK client and API
        self._api_client: Optional[ApiClient] = None
        self._accounting_api: Optional[AccountingApi] = None

    async def __aenter__(self) -> "XeroClient":
        """Async context manager entry - initialize SDK client."""
        await self._initialize_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        # Save tokens on exit to persist any refreshed tokens
        if self._api_client:
            await asyncio.to_thread(self._save_token)

    def _load_token(self) -> Optional[Dict[str, Any]]:
        """Load OAuth2 token dictionary from file if it exists.

        Returns:
            Token dictionary or None if no saved token
        """
        if not self._token_path.exists():
            return None

        try:
            with open(self._token_path, "r") as f:
                token_data = json.load(f)
            logger.debug("Loaded Xero token from file")
            return token_data
        except Exception as e:
            logger.warning(f"Failed to load token from file: {e}")
            return None

    def _save_token(self) -> None:
        """Save OAuth2 token to file for persistence."""
        if not self._api_client:
            return

        try:
            # Get current token from API client
            token = self._api_client.get_oauth2_token()
            if not token:
                return

            # Ensure directory exists
            self._token_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self._token_path, "w") as f:
                json.dump(token, f, indent=2)
            logger.debug("Saved Xero token to file")
        except Exception as e:
            logger.error(f"Failed to save token: {e}")

    def _token_saver_callback(self, token: Dict[str, Any]) -> None:
        """Callback called by SDK when token is refreshed.

        Args:
            token: New token dictionary after refresh
        """
        logger.info("Xero token refreshed automatically by SDK")
        # Save to file
        try:
            self._token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._token_path, "w") as f:
                json.dump(token, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save refreshed token: {e}")

    def _token_getter_callback(self) -> Optional[Dict[str, Any]]:
        """Callback to get current token for SDK.

        Returns:
            Token dictionary
        """
        return self._load_token()

    async def _initialize_client(self) -> None:
        """Initialize the SDK client with OAuth2 token."""
        # Try to load existing token from file
        token = self._load_token()

        # If no saved token, create from settings
        if not token:
            if not self.settings.xero_access_token:
                raise XeroAuthError(
                    "No Xero access token found. Please authorize the app first. "
                    "Set XERO_ACCESS_TOKEN and XERO_REFRESH_TOKEN in .env"
                )

            token = {
                "access_token": self.settings.xero_access_token,
                "refresh_token": self.settings.xero_refresh_token,
                "token_type": "Bearer",
                "expires_in": 1800,  # 30 minutes
                "scope": ["accounting.transactions", "accounting.contacts", "accounting.settings", "offline_access"],
            }

        # Create API client following official SDK pattern
        self._api_client = ApiClient(
            Configuration(
                debug=False,
                oauth2_token=OAuth2Token(
                    client_id=self.settings.xero_client_id,
                    client_secret=self.settings.xero_client_secret,
                ),
            ),
            pool_threads=1,
        )

        # Register token getter/saver callbacks
        self._api_client.oauth2_token_getter(self._token_getter_callback)
        self._api_client.oauth2_token_saver(self._token_saver_callback)

        # Set the token on the client
        self._api_client.set_oauth2_token(token)

        # Refresh the token if needed
        try:
            refreshed_token = await asyncio.to_thread(self._api_client.refresh_oauth2_token)
            logger.info("Xero token refreshed on initialization")
        except Exception as e:
            logger.debug(f"Token refresh on init: {e}")

        # Create Accounting API instance
        self._accounting_api = AccountingApi(self._api_client)

        logger.info("Xero SDK client initialized")

    def _ensure_initialized(self) -> None:
        """Ensure the client is initialized."""
        if not self._accounting_api:
            raise XeroAPIError("Client not initialized. Use async context manager.")

    # =========================================================================
    # CONTACTS (CUSTOMERS)
    # =========================================================================

    async def fetch_contacts(
        self,
        where: Optional[str] = None,
        page: int = 1,
    ) -> List[XeroContact]:
        """Fetch contacts from Xero.

        Args:
            where: Filter expression (e.g., 'EmailAddress=="test@example.com"')
            page: Page number (100 per page)

        Returns:
            List of XeroContact objects
        """
        self._ensure_initialized()

        def _fetch():
            try:
                result = self._accounting_api.get_contacts(
                    xero_tenant_id=self._tenant_id,
                    where=where,
                    page=page,
                )
                return result.contacts or []
            except AccountingBadRequestException as e:
                logger.error(f"Xero API error fetching contacts: {e}")
                raise XeroAPIError(f"Failed to fetch contacts: {e}")

        sdk_contacts = await asyncio.to_thread(_fetch)

        # Convert SDK models to our models
        contacts = []
        for c in sdk_contacts:
            try:
                contacts.append(self._sdk_contact_to_model(c))
            except Exception as e:
                logger.error(f"Failed to convert contact {c.contact_id}: {e}")

        logger.info(f"Fetched {len(contacts)} contacts from Xero")
        return contacts

    async def find_contact_by_email(self, email: str) -> Optional[XeroContact]:
        """Find a contact by email address.

        Args:
            email: Email address to search for

        Returns:
            XeroContact or None if not found
        """
        if not email:
            return None

        # Escape quotes in email for filter
        safe_email = email.replace('"', '\\"')
        where = f'EmailAddress=="{safe_email}"'

        contacts = await self.fetch_contacts(where=where)
        return contacts[0] if contacts else None

    async def create_contact(self, contact: XeroContact) -> XeroContact:
        """Create a new contact in Xero.

        Args:
            contact: XeroContact to create

        Returns:
            Created XeroContact with ID populated
        """
        self._ensure_initialized()

        sdk_contact = self._model_to_sdk_contact(contact)
        contacts_payload = Contacts(contacts=[sdk_contact])

        def _create():
            try:
                result = self._accounting_api.create_contacts(
                    xero_tenant_id=self._tenant_id,
                    contacts=contacts_payload,
                )
                if result.contacts:
                    return result.contacts[0]
                raise XeroAPIError("Contact creation returned no data")
            except AccountingBadRequestException as e:
                raise XeroAPIError(f"Failed to create contact: {e}")

        created = await asyncio.to_thread(_create)
        result = self._sdk_contact_to_model(created)

        logger.info(f"Created Xero contact: {result.ContactID} ({result.Name})")
        return result

    async def update_contact(self, contact: XeroContact) -> XeroContact:
        """Update an existing contact in Xero.

        Args:
            contact: XeroContact with ContactID set

        Returns:
            Updated XeroContact
        """
        self._ensure_initialized()

        if not contact.ContactID:
            raise XeroAPIError("Contact ID required for update")

        sdk_contact = self._model_to_sdk_contact(contact)
        
        # Debug logging
        logger.debug(
            f"Updating contact {contact.ContactID}: "
            f"IsCustomer={sdk_contact.is_customer}, IsSupplier={sdk_contact.is_supplier}"
        )
        
        contacts_payload = Contacts(contacts=[sdk_contact])

        def _update():
            try:
                result = self._accounting_api.update_contact(
                    xero_tenant_id=self._tenant_id,
                    contact_id=contact.ContactID,
                    contacts=contacts_payload,
                )
                if result.contacts:
                    return result.contacts[0]
                raise XeroAPIError("Contact update returned no data")
            except AccountingBadRequestException as e:
                raise XeroAPIError(f"Failed to update contact: {e}")

        updated = await asyncio.to_thread(_update)
        result = self._sdk_contact_to_model(updated)

        logger.info(
            f"Updated Xero contact: {result.ContactID} ({result.Name}) "
            f"IsCustomer={result.IsCustomer}"
        )
        return result

    async def get_contact(self, contact_id: str) -> Optional[XeroContact]:
        """Fetch a single contact by ID.

        Args:
            contact_id: Xero contact ID

        Returns:
            XeroContact or None if not found
        """
        self._ensure_initialized()

        def _get():
            try:
                result = self._accounting_api.get_contact(
                    xero_tenant_id=self._tenant_id,
                    contact_id=contact_id,
                )
                if result.contacts:
                    return result.contacts[0]
                return None
            except AccountingBadRequestException:
                return None

        sdk_contact = await asyncio.to_thread(_get)
        if sdk_contact:
            return self._sdk_contact_to_model(sdk_contact)
        return None

    # =========================================================================
    # ITEMS (PRODUCTS)
    # =========================================================================

    async def fetch_items(
        self,
        where: Optional[str] = None,
    ) -> List[XeroItem]:
        """Fetch items from Xero.

        Args:
            where: Filter expression

        Returns:
            List of XeroItem objects
        """
        self._ensure_initialized()

        def _fetch():
            try:
                result = self._accounting_api.get_items(
                    xero_tenant_id=self._tenant_id,
                    where=where,
                )
                return result.items or []
            except AccountingBadRequestException as e:
                raise XeroAPIError(f"Failed to fetch items: {e}")

        sdk_items = await asyncio.to_thread(_fetch)

        items = []
        for item in sdk_items:
            try:
                items.append(self._sdk_item_to_model(item))
            except Exception as e:
                logger.error(f"Failed to convert item {item.item_id}: {e}")

        logger.info(f"Fetched {len(items)} items from Xero")
        return items

    async def find_item_by_code(self, code: str) -> Optional[XeroItem]:
        """Find an item by code (SKU).

        Args:
            code: Item code (SKU) to search for

        Returns:
            XeroItem or None if not found
        """
        if not code:
            return None

        safe_code = code.replace('"', '\\"')
        where = f'Code=="{safe_code}"'

        items = await self.fetch_items(where=where)
        return items[0] if items else None

    async def get_item_by_id(self, item_id: str) -> Optional[XeroItem]:
        """Get an item by its Xero ItemID.

        Args:
            item_id: Xero ItemID

        Returns:
            XeroItem or None if not found
        """
        if not item_id:
            return None

        self._ensure_initialized()

        def _fetch():
            try:
                result = self._accounting_api.get_items(
                    xero_tenant_id=self._tenant_id,
                    where=f'ItemID==GUID("{item_id}")',
                )
                return result.items or []
            except AccountingBadRequestException as e:
                raise XeroAPIError(f"Failed to fetch item: {e}")

        sdk_items = await asyncio.to_thread(_fetch)

        if sdk_items:
            try:
                return self._sdk_item_to_model(sdk_items[0])
            except Exception as e:
                logger.error(f"Failed to convert item {item_id}: {e}")
                return None
        
        return None

    async def create_item(self, item: XeroItem) -> XeroItem:
        """Create a new item in Xero.

        Args:
            item: XeroItem to create

        Returns:
            Created XeroItem with ID populated
        """
        self._ensure_initialized()

        sdk_item = self._model_to_sdk_item(item)
        items_payload = Items(items=[sdk_item])

        def _create():
            try:
                result = self._accounting_api.create_items(
                    xero_tenant_id=self._tenant_id,
                    items=items_payload,
                )
                if result.items:
                    return result.items[0]
                raise XeroAPIError("Item creation returned no data")
            except AccountingBadRequestException as e:
                raise XeroAPIError(f"Failed to create item: {e}")

        created = await asyncio.to_thread(_create)
        result = self._sdk_item_to_model(created)

        logger.info(f"Created Xero item: {result.ItemID} ({result.Code})")
        return result

    async def update_item(self, item: XeroItem) -> XeroItem:
        """Update an existing item in Xero.

        Args:
            item: XeroItem with ItemID set

        Returns:
            Updated XeroItem
        """
        self._ensure_initialized()

        if not item.ItemID:
            raise XeroAPIError("Item ID required for update")

        sdk_item = self._model_to_sdk_item(item)
        items_payload = Items(items=[sdk_item])

        def _update():
            try:
                result = self._accounting_api.update_item(
                    xero_tenant_id=self._tenant_id,
                    item_id=item.ItemID,
                    items=items_payload,
                )
                if result.items:
                    return result.items[0]
                raise XeroAPIError("Item update returned no data")
            except AccountingBadRequestException as e:
                raise XeroAPIError(f"Failed to update item: {e}")

        updated = await asyncio.to_thread(_update)
        result = self._sdk_item_to_model(updated)

        logger.info(f"Updated Xero item: {result.ItemID}")
        return result

    # =========================================================================
    # INVOICES (ORDERS)
    # =========================================================================

    async def fetch_invoices(
        self,
        where: Optional[str] = None,
        page: int = 1,
    ) -> List[XeroInvoice]:
        """Fetch invoices from Xero.

        Args:
            where: Filter expression
            page: Page number

        Returns:
            List of XeroInvoice objects
        """
        self._ensure_initialized()

        def _fetch():
            try:
                result = self._accounting_api.get_invoices(
                    xero_tenant_id=self._tenant_id,
                    where=where,
                    page=page,
                )
                return result.invoices or []
            except AccountingBadRequestException as e:
                raise XeroAPIError(f"Failed to fetch invoices: {e}")

        sdk_invoices = await asyncio.to_thread(_fetch)

        invoices = []
        for inv in sdk_invoices:
            try:
                invoices.append(self._sdk_invoice_to_model(inv))
            except Exception as e:
                logger.error(f"Failed to convert invoice {inv.invoice_id}: {e}")

        logger.info(f"Fetched {len(invoices)} invoices from Xero")
        return invoices

    async def find_invoice_by_reference(self, reference: str) -> Optional[XeroInvoice]:
        """Find an invoice by reference (Shopify order number).

        Args:
            reference: Invoice reference to search for

        Returns:
            XeroInvoice or None if not found
        """
        if not reference:
            return None

        safe_ref = reference.replace('"', '\\"')
        where = f'Reference=="{safe_ref}"'

        invoices = await self.fetch_invoices(where=where)
        return invoices[0] if invoices else None

    async def create_invoice(self, invoice: XeroInvoice) -> XeroInvoice:
        """Create a new invoice in Xero.

        Args:
            invoice: XeroInvoice to create

        Returns:
            Created XeroInvoice with ID populated
        """
        self._ensure_initialized()

        sdk_invoice = self._model_to_sdk_invoice(invoice)
        invoices_payload = Invoices(invoices=[sdk_invoice])

        def _create():
            try:
                result = self._accounting_api.create_invoices(
                    xero_tenant_id=self._tenant_id,
                    invoices=invoices_payload,
                )
                if result.invoices:
                    return result.invoices[0]
                raise XeroAPIError("Invoice creation returned no data")
            except AccountingBadRequestException as e:
                raise XeroAPIError(f"Failed to create invoice: {e}")

        created = await asyncio.to_thread(_create)
        result = self._sdk_invoice_to_model(created)

        logger.info(f"Created Xero invoice: {result.InvoiceID} ({result.Reference})")
        return result

    # =========================================================================
    # HEALTH CHECK
    # =========================================================================

    async def check_connection(self) -> bool:
        """Verify API connection is working.

        Returns:
            True if connection is successful
        """
        try:
            self._ensure_initialized()

            def _check():
                try:
                    result = self._accounting_api.get_organisations(
                        xero_tenant_id=self._tenant_id
                    )
                    return result.organisations is not None
                except Exception as e:
                    logger.error(f"Xero connection check failed: {e}")
                    return False

            success = await asyncio.to_thread(_check)

            if success:
                logger.info("Xero API connection successful")
            else:
                logger.error("Xero API connection failed")

            return success
        except Exception as e:
            logger.error(f"Xero API connection failed: {e}")
            return False

    async def get_tax_rates(self) -> List[dict]:
        """Fetch all tax rates from Xero.

        Returns:
            List of tax rate dictionaries with TaxType, Name, EffectiveRate, Status
        """
        self._ensure_initialized()

        def _fetch():
            try:
                result = self._accounting_api.get_tax_rates(
                    xero_tenant_id=self._tenant_id
                )
                return result.tax_rates or []
            except Exception as e:
                raise XeroAPIError(f"Failed to fetch tax rates: {e}")

        sdk_tax_rates = await asyncio.to_thread(_fetch)

        tax_rates = []
        for rate in sdk_tax_rates:
            tax_rates.append({
                "TaxType": rate.tax_type,
                "Name": rate.name,
                "EffectiveRate": rate.effective_rate,
                "Status": rate.status,
                "DisplayTaxRate": rate.display_tax_rate,
                "CanApplyToAssets": rate.can_apply_to_assets,
                "CanApplyToEquity": rate.can_apply_to_equity,
                "CanApplyToExpenses": rate.can_apply_to_expenses,
                "CanApplyToLiabilities": rate.can_apply_to_liabilities,
                "CanApplyToRevenue": rate.can_apply_to_revenue,
            })

        return tax_rates

    async def get_tenant_info(self) -> dict:
        """Get information about the connected Xero tenant.

        Returns:
            Organisation information
        """
        self._ensure_initialized()

        def _get():
            result = self._accounting_api.get_organisations(
                xero_tenant_id=self._tenant_id
            )
            if result.organisations:
                org = result.organisations[0]
                return {
                    "name": org.name,
                    "legal_name": org.legal_name,
                    "country_code": org.country_code,
                    "base_currency": org.base_currency,
                }
            return {}

        return await asyncio.to_thread(_get)

    # =========================================================================
    # MODEL CONVERSION HELPERS
    # =========================================================================

    def _sdk_contact_to_model(self, sdk_contact: Contact) -> XeroContact:
        """Convert SDK Contact to our XeroContact model."""
        addresses = []
        if sdk_contact.addresses:
            for addr in sdk_contact.addresses:
                addresses.append(XeroAddress(
                    AddressType=addr.address_type or "POBOX",
                    AddressLine1=addr.address_line1,
                    AddressLine2=addr.address_line2,
                    City=addr.city,
                    Region=addr.region,
                    PostalCode=addr.postal_code,
                    Country=addr.country,
                ))

        phones = []
        if sdk_contact.phones:
            for phone in sdk_contact.phones:
                phones.append(XeroPhone(
                    PhoneType=phone.phone_type or "DEFAULT",
                    PhoneNumber=phone.phone_number,
                    PhoneAreaCode=phone.phone_area_code,
                    PhoneCountryCode=phone.phone_country_code,
                ))

        return XeroContact(
            ContactID=sdk_contact.contact_id,
            ContactNumber=sdk_contact.contact_number,
            ContactStatus=sdk_contact.contact_status or "ACTIVE",
            Name=sdk_contact.name or "",
            FirstName=sdk_contact.first_name,
            LastName=sdk_contact.last_name,
            EmailAddress=sdk_contact.email_address,
            Addresses=addresses,
            Phones=phones,
            IsCustomer=sdk_contact.is_customer or False,
            IsSupplier=sdk_contact.is_supplier or False,
            UpdatedDateUTC=sdk_contact.updated_date_utc,
        )

    def _model_to_sdk_contact(self, contact: XeroContact) -> Contact:
        """Convert our XeroContact model to SDK Contact."""
        addresses = None
        if contact.Addresses:
            addresses = [
                Address(
                    address_type=addr.AddressType,
                    address_line1=addr.AddressLine1,
                    address_line2=addr.AddressLine2,
                    city=addr.City,
                    region=addr.Region,
                    postal_code=addr.PostalCode,
                    country=addr.Country,
                )
                for addr in contact.Addresses
            ]

        phones = None
        if contact.Phones:
            phones = [
                Phone(
                    phone_type=phone.PhoneType,
                    phone_number=phone.PhoneNumber,
                    phone_area_code=phone.PhoneAreaCode,
                    phone_country_code=phone.PhoneCountryCode,
                )
                for phone in contact.Phones
            ]

        sdk_contact = Contact(
            contact_id=contact.ContactID,
            contact_status=contact.ContactStatus,
            name=contact.Name,
            first_name=contact.FirstName,
            last_name=contact.LastName,
            email_address=contact.EmailAddress,
            addresses=addresses,
            phones=phones,
            is_customer=contact.IsCustomer,
            is_supplier=contact.IsSupplier,
        )
        
        # Debug: log what we're sending
        logger.info(f"SDK Contact: is_customer={sdk_contact.is_customer}, is_supplier={sdk_contact.is_supplier}")
        
        return sdk_contact

    def _sdk_item_to_model(self, sdk_item: Item) -> XeroItem:
        """Convert SDK Item to our XeroItem model."""
        sales_details = None
        if sdk_item.sales_details:
            sales_details = {
                "UnitPrice": sdk_item.sales_details.unit_price,
                "AccountCode": sdk_item.sales_details.account_code,
                "TaxType": sdk_item.sales_details.tax_type,
            }

        purchase_details = None
        if sdk_item.purchase_details:
            purchase_details = {
                "UnitPrice": sdk_item.purchase_details.unit_price,
                "AccountCode": sdk_item.purchase_details.account_code,
                "TaxType": sdk_item.purchase_details.tax_type,
            }

        return XeroItem(
            ItemID=sdk_item.item_id,
            Code=sdk_item.code or "",
            Name=sdk_item.name or "",
            Description=sdk_item.description,
            PurchaseDescription=sdk_item.purchase_description,
            PurchaseDetails=purchase_details,
            SalesDetails=sales_details,
            IsTrackedAsInventory=sdk_item.is_tracked_as_inventory or False,
            IsSold=sdk_item.is_sold or False,
            IsPurchased=sdk_item.is_purchased or False,
            UpdatedDateUTC=sdk_item.updated_date_utc,
        )

    def _model_to_sdk_item(self, item: XeroItem) -> Item:
        """Convert our XeroItem model to SDK Item."""
        from xero_python.accounting import Purchase

        sales_details = None
        if item.SalesDetails:
            sales_details = Purchase(
                unit_price=item.SalesDetails.get("UnitPrice"),
                account_code=item.SalesDetails.get("AccountCode"),
                tax_type=item.SalesDetails.get("TaxType"),
            )

        purchase_details = None
        if item.PurchaseDetails:
            purchase_details = Purchase(
                unit_price=item.PurchaseDetails.get("UnitPrice"),
                account_code=item.PurchaseDetails.get("AccountCode"),
                tax_type=item.PurchaseDetails.get("TaxType"),
            )

        return Item(
            item_id=item.ItemID,
            code=item.Code,
            name=item.Name,
            description=item.Description,
            purchase_description=item.PurchaseDescription,
            purchase_details=purchase_details,
            sales_details=sales_details,
            is_sold=item.IsSold,
            is_purchased=item.IsPurchased,
        )

    def _sdk_invoice_to_model(self, sdk_invoice: Invoice) -> XeroInvoice:
        """Convert SDK Invoice to our XeroInvoice model."""
        line_items = []
        if sdk_invoice.line_items:
            for li in sdk_invoice.line_items:
                line_items.append(XeroLineItem(
                    Description=li.description or "",
                    Quantity=li.quantity or 1.0,
                    UnitAmount=li.unit_amount or 0.0,
                    AccountCode=li.account_code or "200",
                    ItemCode=li.item_code,
                    TaxType=li.tax_type or "OUTPUT2",
                    LineAmount=li.line_amount,
                ))

        return XeroInvoice(
            InvoiceID=sdk_invoice.invoice_id,
            InvoiceNumber=sdk_invoice.invoice_number,
            Reference=sdk_invoice.reference,
            Type=sdk_invoice.type or "ACCREC",
            Status=sdk_invoice.status or "DRAFT",
            ContactID=sdk_invoice.contact.contact_id if sdk_invoice.contact else None,
            LineItems=line_items,
            Date=sdk_invoice.date,
            DueDate=sdk_invoice.due_date,
            CurrencyCode=sdk_invoice.currency_code or "GBP",
            SubTotal=sdk_invoice.sub_total,
            TotalTax=sdk_invoice.total_tax,
            Total=sdk_invoice.total,
            UpdatedDateUTC=sdk_invoice.updated_date_utc,
        )

    def _model_to_sdk_invoice(self, invoice: XeroInvoice) -> Invoice:
        """Convert our XeroInvoice model to SDK Invoice."""
        line_items = None
        if invoice.LineItems:
            line_items = [
                LineItem(
                    description=li.Description,
                    quantity=li.Quantity,
                    unit_amount=li.UnitAmount,
                    account_code=li.AccountCode,
                    item_code=li.ItemCode,
                    tax_type=li.TaxType,
                )
                for li in invoice.LineItems
            ]

        contact = None
        if invoice.ContactID:
            contact = Contact(contact_id=invoice.ContactID)

        return Invoice(
            invoice_id=invoice.InvoiceID,
            reference=invoice.Reference,
            type=invoice.Type,
            status=invoice.Status,
            contact=contact,
            line_items=line_items,
            date=invoice.Date,
            due_date=invoice.DueDate,
            currency_code=invoice.CurrencyCode,
        )
