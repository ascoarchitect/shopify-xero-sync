"""Unit tests for Xero API client.

Tests verify that:
- OAuth2 token refresh works correctly
- API requests are properly formatted
- Rate limiting is handled correctly
- Authentication errors are detected
- Duplicate detection queries work correctly
- Error scenarios are handled gracefully
"""

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from datetime import datetime, timedelta
import httpx

from src.xero_client import (
    XeroClient,
    XeroAPIError,
    XeroRateLimitError,
    XeroAuthError,
)
from src.config import Settings
from src.models import XeroContact, XeroItem, XeroInvoice, XeroLineItem

from tests.fixtures.xero_fixtures import (
    make_xero_contact,
    make_xero_contacts_response,
    make_xero_item,
    make_xero_items_response,
    make_xero_invoice,
    make_xero_invoices_response,
    make_empty_contacts_response,
    make_empty_items_response,
    make_empty_invoices_response,
    XERO_ORGANISATION,
    XERO_TOKEN_RESPONSE,
    XERO_TOKEN_ERROR,
    XERO_ERROR_AUTH,
    XERO_ERROR_FORBIDDEN,
    XERO_ERROR_NOT_FOUND,
    XERO_ERROR_RATE_LIMIT,
    XERO_ERROR_VALIDATION,
    XERO_ERROR_DUPLICATE_CONTACT,
)


@pytest.fixture
def mock_settings(mock_env_vars, monkeypatch):
    """Create settings with mock environment variables and tokens."""
    monkeypatch.setenv("XERO_ACCESS_TOKEN", "test_access_token")
    monkeypatch.setenv("XERO_REFRESH_TOKEN", "test_refresh_token")
    return Settings()


class TestXeroClientInit:
    """Tests for XeroClient initialization."""

    def test_client_init(self, mock_settings):
        """Test client initializes correctly."""
        client = XeroClient(mock_settings)

        assert client.settings == mock_settings
        assert client._access_token == "test_access_token"
        assert client._refresh_token == "test_refresh_token"

    def test_client_rate_limit_from_settings(self, mock_settings):
        """Test rate limit delay comes from settings."""
        client = XeroClient(mock_settings)

        assert client.rate_limit_delay == mock_settings.xero_rate_limit_delay


class TestXeroClientContextManager:
    """Tests for async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_creates_client(self, mock_settings):
        """Test context manager creates httpx client."""
        client = XeroClient(mock_settings)

        async with client as c:
            assert c._client is not None

    @pytest.mark.asyncio
    async def test_context_manager_closes_client(self, mock_settings):
        """Test context manager closes httpx client on exit."""
        client = XeroClient(mock_settings)

        async with client as c:
            assert c._client is not None

        assert client._client is None


class TestTokenRefresh:
    """Tests for OAuth2 token refresh."""

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, mock_settings, httpx_mock):
        """Test successful token refresh."""
        httpx_mock.add_response(
            method="POST",
            url="https://identity.xero.com/connect/token",
            json=XERO_TOKEN_RESPONSE,
        )

        async with XeroClient(mock_settings) as client:
            result = await client.refresh_access_token()

        assert result is True
        assert client._access_token == XERO_TOKEN_RESPONSE["access_token"]

    @pytest.mark.asyncio
    async def test_refresh_token_failure(self, mock_settings, httpx_mock):
        """Test token refresh failure."""
        httpx_mock.add_response(
            method="POST",
            url="https://identity.xero.com/connect/token",
            status_code=400,
            json=XERO_TOKEN_ERROR,
        )

        async with XeroClient(mock_settings) as client:
            with pytest.raises(XeroAuthError):
                await client.refresh_access_token()

    @pytest.mark.asyncio
    async def test_refresh_token_no_refresh_token(self, mock_settings):
        """Test error when no refresh token available."""
        mock_settings.xero_refresh_token = None
        client = XeroClient(mock_settings)
        client._refresh_token = None

        async with client:
            with pytest.raises(XeroAuthError) as exc_info:
                await client.refresh_access_token()

        assert "No refresh token" in str(exc_info.value)


class TestFetchContacts:
    """Tests for fetching contacts."""

    @pytest.mark.asyncio
    async def test_fetch_contacts_success(self, mock_settings, httpx_mock):
        """Test successful contacts fetch."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/Contacts.*",
            json=make_xero_contacts_response(),
            headers={"X-Rate-Limit-Remaining": "59"},
        )

        async with XeroClient(mock_settings) as client:
            contacts = await client.fetch_contacts()

        assert len(contacts) == 2

    @pytest.mark.asyncio
    async def test_fetch_contacts_with_filter(self, mock_settings, httpx_mock):
        """Test contacts fetch with OData filter."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/Contacts.*where=.*",
            json=make_xero_contacts_response([
                make_xero_contact(email="specific@example.com")
            ]),
            headers={"X-Rate-Limit-Remaining": "59"},
        )

        async with XeroClient(mock_settings) as client:
            contacts = await client.fetch_contacts(where='EmailAddress=="specific@example.com"')

        assert len(contacts) == 1


class TestFindContactByEmail:
    """Tests for finding contact by email (duplicate detection)."""

    @pytest.mark.asyncio
    async def test_find_contact_by_email_found(self, mock_settings, httpx_mock):
        """Test finding existing contact by email."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/Contacts.*EmailAddress==.*",
            json=make_xero_contacts_response([
                make_xero_contact(email="existing@example.com")
            ]),
            headers={"X-Rate-Limit-Remaining": "59"},
        )

        async with XeroClient(mock_settings) as client:
            contact = await client.find_contact_by_email("existing@example.com")

        assert contact is not None
        assert contact.EmailAddress == "existing@example.com"

    @pytest.mark.asyncio
    async def test_find_contact_by_email_not_found(self, mock_settings, httpx_mock):
        """Test contact not found by email."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/Contacts.*",
            json=make_empty_contacts_response(),
            headers={"X-Rate-Limit-Remaining": "59"},
        )

        async with XeroClient(mock_settings) as client:
            contact = await client.find_contact_by_email("notfound@example.com")

        assert contact is None

    @pytest.mark.asyncio
    async def test_find_contact_by_email_none(self, mock_settings):
        """Test None email returns None."""
        async with XeroClient(mock_settings) as client:
            contact = await client.find_contact_by_email(None)

        assert contact is None

    @pytest.mark.asyncio
    async def test_find_contact_by_email_empty(self, mock_settings):
        """Test empty email returns None."""
        async with XeroClient(mock_settings) as client:
            contact = await client.find_contact_by_email("")

        assert contact is None


class TestCreateContact:
    """Tests for creating contacts."""

    @pytest.mark.asyncio
    async def test_create_contact_success(self, mock_settings, httpx_mock):
        """Test successful contact creation."""
        created_contact = make_xero_contact(
            contact_id="new-contact-id",
            name="New Customer",
            email="new@example.com",
        )
        httpx_mock.add_response(
            method="POST",
            url__regex=r".*/Contacts.*",
            json={"Contacts": [created_contact]},
            headers={"X-Rate-Limit-Remaining": "59"},
        )

        contact = XeroContact(Name="New Customer", EmailAddress="new@example.com")

        async with XeroClient(mock_settings) as client:
            result = await client.create_contact(contact)

        assert result.ContactID == "new-contact-id"

    @pytest.mark.asyncio
    async def test_create_contact_no_data_returned(self, mock_settings, httpx_mock):
        """Test error when creation returns no data."""
        httpx_mock.add_response(
            method="POST",
            url__regex=r".*/Contacts.*",
            json={"Contacts": []},
            headers={"X-Rate-Limit-Remaining": "59"},
        )

        contact = XeroContact(Name="New Customer")

        async with XeroClient(mock_settings) as client:
            with pytest.raises(XeroAPIError) as exc_info:
                await client.create_contact(contact)

        assert "no data" in str(exc_info.value).lower()


class TestUpdateContact:
    """Tests for updating contacts."""

    @pytest.mark.asyncio
    async def test_update_contact_success(self, mock_settings, httpx_mock):
        """Test successful contact update."""
        updated_contact = make_xero_contact(
            contact_id="existing-id",
            name="Updated Name",
        )
        httpx_mock.add_response(
            method="POST",
            url__regex=r".*/Contacts.*",
            json={"Contacts": [updated_contact]},
            headers={"X-Rate-Limit-Remaining": "59"},
        )

        contact = XeroContact(ContactID="existing-id", Name="Updated Name")

        async with XeroClient(mock_settings) as client:
            result = await client.update_contact(contact)

        assert result.Name == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_contact_no_id(self, mock_settings):
        """Test error when updating contact without ID."""
        contact = XeroContact(Name="No ID Contact")

        async with XeroClient(mock_settings) as client:
            with pytest.raises(XeroAPIError) as exc_info:
                await client.update_contact(contact)

        assert "ID required" in str(exc_info.value)


class TestFetchItems:
    """Tests for fetching items."""

    @pytest.mark.asyncio
    async def test_fetch_items_success(self, mock_settings, httpx_mock):
        """Test successful items fetch."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/Items.*",
            json=make_xero_items_response(),
            headers={"X-Rate-Limit-Remaining": "59"},
        )

        async with XeroClient(mock_settings) as client:
            items = await client.fetch_items()

        assert len(items) == 3


class TestFindItemByCode:
    """Tests for finding item by code (duplicate detection)."""

    @pytest.mark.asyncio
    async def test_find_item_by_code_found(self, mock_settings, httpx_mock):
        """Test finding existing item by code."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/Items.*Code==.*",
            json=make_xero_items_response([
                make_xero_item(code="WM-001")
            ]),
            headers={"X-Rate-Limit-Remaining": "59"},
        )

        async with XeroClient(mock_settings) as client:
            item = await client.find_item_by_code("WM-001")

        assert item is not None
        assert item.Code == "WM-001"

    @pytest.mark.asyncio
    async def test_find_item_by_code_not_found(self, mock_settings, httpx_mock):
        """Test item not found by code."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/Items.*",
            json=make_empty_items_response(),
            headers={"X-Rate-Limit-Remaining": "59"},
        )

        async with XeroClient(mock_settings) as client:
            item = await client.find_item_by_code("NOTFOUND")

        assert item is None

    @pytest.mark.asyncio
    async def test_find_item_by_code_none(self, mock_settings):
        """Test None code returns None."""
        async with XeroClient(mock_settings) as client:
            item = await client.find_item_by_code(None)

        assert item is None


class TestCreateItem:
    """Tests for creating items."""

    @pytest.mark.asyncio
    async def test_create_item_success(self, mock_settings, httpx_mock):
        """Test successful item creation."""
        created_item = make_xero_item(item_id="new-item-id", code="NEW-001")
        httpx_mock.add_response(
            method="POST",
            url__regex=r".*/Items.*",
            json={"Items": [created_item]},
            headers={"X-Rate-Limit-Remaining": "59"},
        )

        item = XeroItem(Code="NEW-001", Name="New Item")

        async with XeroClient(mock_settings) as client:
            result = await client.create_item(item)

        assert result.ItemID == "new-item-id"


class TestUpdateItem:
    """Tests for updating items."""

    @pytest.mark.asyncio
    async def test_update_item_success(self, mock_settings, httpx_mock):
        """Test successful item update."""
        updated_item = make_xero_item(item_id="existing-id", name="Updated Item")
        httpx_mock.add_response(
            method="POST",
            url__regex=r".*/Items.*",
            json={"Items": [updated_item]},
            headers={"X-Rate-Limit-Remaining": "59"},
        )

        item = XeroItem(ItemID="existing-id", Code="WM-001", Name="Updated Item")

        async with XeroClient(mock_settings) as client:
            result = await client.update_item(item)

        assert result.Name == "Updated Item"

    @pytest.mark.asyncio
    async def test_update_item_no_id(self, mock_settings):
        """Test error when updating item without ID."""
        item = XeroItem(Code="NO-ID", Name="No ID Item")

        async with XeroClient(mock_settings) as client:
            with pytest.raises(XeroAPIError) as exc_info:
                await client.update_item(item)

        assert "ID required" in str(exc_info.value)


class TestFetchInvoices:
    """Tests for fetching invoices."""

    @pytest.mark.asyncio
    async def test_fetch_invoices_success(self, mock_settings, httpx_mock):
        """Test successful invoices fetch."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/Invoices.*",
            json=make_xero_invoices_response(),
            headers={"X-Rate-Limit-Remaining": "59"},
        )

        async with XeroClient(mock_settings) as client:
            invoices = await client.fetch_invoices()

        assert len(invoices) == 2


class TestFindInvoiceByReference:
    """Tests for finding invoice by reference (duplicate detection)."""

    @pytest.mark.asyncio
    async def test_find_invoice_by_reference_found(self, mock_settings, httpx_mock):
        """Test finding existing invoice by reference."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/Invoices.*Reference==.*",
            json=make_xero_invoices_response([
                make_xero_invoice(reference="SHOP-1001")
            ]),
            headers={"X-Rate-Limit-Remaining": "59"},
        )

        async with XeroClient(mock_settings) as client:
            invoice = await client.find_invoice_by_reference("SHOP-1001")

        assert invoice is not None
        assert invoice.Reference == "SHOP-1001"

    @pytest.mark.asyncio
    async def test_find_invoice_by_reference_not_found(self, mock_settings, httpx_mock):
        """Test invoice not found by reference."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/Invoices.*",
            json=make_empty_invoices_response(),
            headers={"X-Rate-Limit-Remaining": "59"},
        )

        async with XeroClient(mock_settings) as client:
            invoice = await client.find_invoice_by_reference("NOTFOUND")

        assert invoice is None


class TestCreateInvoice:
    """Tests for creating invoices."""

    @pytest.mark.asyncio
    async def test_create_invoice_success(self, mock_settings, httpx_mock):
        """Test successful invoice creation."""
        created_invoice = make_xero_invoice(
            invoice_id="new-invoice-id",
            reference="SHOP-1001",
        )
        httpx_mock.add_response(
            method="POST",
            url__regex=r".*/Invoices.*",
            json={"Invoices": [created_invoice]},
            headers={"X-Rate-Limit-Remaining": "59"},
        )

        invoice = XeroInvoice(
            Reference="SHOP-1001",
            ContactID="contact-123",
            LineItems=[XeroLineItem(Description="Test", Quantity=1, UnitAmount=10.0)],
        )

        async with XeroClient(mock_settings) as client:
            result = await client.create_invoice(invoice)

        assert result.InvoiceID == "new-invoice-id"


class TestCheckConnection:
    """Tests for connection check."""

    @pytest.mark.asyncio
    async def test_check_connection_success(self, mock_settings, httpx_mock):
        """Test successful connection check."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/Organisation.*",
            json=XERO_ORGANISATION,
            headers={"X-Rate-Limit-Remaining": "59"},
        )

        async with XeroClient(mock_settings) as client:
            result = await client.check_connection()

        assert result is True

    @pytest.mark.asyncio
    async def test_check_connection_failure(self, mock_settings, httpx_mock):
        """Test connection check failure."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/Organisation.*",
            status_code=401,
            json=XERO_ERROR_AUTH,
        )

        async with XeroClient(mock_settings) as client:
            result = await client.check_connection()

        assert result is False


class TestGetTenantInfo:
    """Tests for tenant info retrieval."""

    @pytest.mark.asyncio
    async def test_get_tenant_info(self, mock_settings, httpx_mock):
        """Test getting tenant information."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/Organisation.*",
            json=XERO_ORGANISATION,
            headers={"X-Rate-Limit-Remaining": "59"},
        )

        async with XeroClient(mock_settings) as client:
            info = await client.get_tenant_info()

        assert info["Name"] == "Wax Pop Ltd"


class TestErrorHandling:
    """Tests for error handling scenarios."""

    @pytest.mark.asyncio
    async def test_auth_error(self, mock_settings, httpx_mock):
        """Test authentication error handling."""
        # First: trigger 401
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/Contacts.*",
            status_code=401,
            json=XERO_ERROR_AUTH,
        )
        # Second: token refresh fails
        httpx_mock.add_response(
            method="POST",
            url="https://identity.xero.com/connect/token",
            status_code=400,
            json=XERO_TOKEN_ERROR,
        )

        async with XeroClient(mock_settings) as client:
            with pytest.raises(XeroAuthError):
                await client.fetch_contacts()

    @pytest.mark.asyncio
    async def test_forbidden_error(self, mock_settings, httpx_mock):
        """Test 403 forbidden error."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/Contacts.*",
            status_code=403,
            json=XERO_ERROR_FORBIDDEN,
        )

        async with XeroClient(mock_settings) as client:
            with pytest.raises(XeroAuthError) as exc_info:
                await client.fetch_contacts()

        assert "forbidden" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_not_found_error(self, mock_settings, httpx_mock):
        """Test 404 not found error."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/Contacts/nonexistent.*",
            status_code=404,
            json=XERO_ERROR_NOT_FOUND,
        )

        async with XeroClient(mock_settings) as client:
            with pytest.raises(XeroAPIError) as exc_info:
                await client.get_contact("nonexistent")

        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_validation_error(self, mock_settings, httpx_mock):
        """Test validation error handling."""
        httpx_mock.add_response(
            method="POST",
            url__regex=r".*/Contacts.*",
            status_code=400,
            json=XERO_ERROR_VALIDATION,
        )

        contact = XeroContact(Name="Test", EmailAddress="invalid")

        async with XeroClient(mock_settings) as client:
            with pytest.raises(XeroAPIError) as exc_info:
                await client.create_contact(contact)

        assert "unique" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_rate_limit_retry(self, mock_settings, httpx_mock):
        """Test rate limit triggers retry."""
        # First: rate limit
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/Contacts.*",
            status_code=429,
            headers={"Retry-After": "0.1"},
        )
        # Second: success
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/Contacts.*",
            json=make_xero_contacts_response([]),
            headers={"X-Rate-Limit-Remaining": "59"},
        )

        async with XeroClient(mock_settings) as client:
            contacts = await client.fetch_contacts()

        assert len(contacts) == 0
        assert len(httpx_mock.get_requests()) == 2

    @pytest.mark.asyncio
    async def test_timeout_retry(self, mock_settings, httpx_mock):
        """Test timeout triggers retry."""
        # First: timeout
        httpx_mock.add_exception(httpx.TimeoutException("Timeout"))
        # Second: success
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/Contacts.*",
            json=make_xero_contacts_response([]),
            headers={"X-Rate-Limit-Remaining": "59"},
        )

        async with XeroClient(mock_settings) as client:
            contacts = await client.fetch_contacts()

        assert len(contacts) == 0

    @pytest.mark.asyncio
    async def test_client_not_initialized_error(self, mock_settings):
        """Test error when client not initialized."""
        client = XeroClient(mock_settings)

        with pytest.raises(XeroAPIError) as exc_info:
            await client._request("GET", "/Test")

        assert "not initialized" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_no_access_token_error(self, mock_settings):
        """Test error when no access token."""
        mock_settings.xero_access_token = None
        client = XeroClient(mock_settings)
        client._access_token = None

        async with client:
            with pytest.raises(XeroAuthError) as exc_info:
                await client._ensure_valid_token()

        assert "No access token" in str(exc_info.value)


class TestErrorMessageExtraction:
    """Tests for error message extraction."""

    @pytest.mark.asyncio
    async def test_extract_validation_errors(self, mock_settings, httpx_mock):
        """Test extraction of validation error messages."""
        httpx_mock.add_response(
            method="POST",
            url__regex=r".*/Contacts.*",
            status_code=400,
            json=XERO_ERROR_DUPLICATE_CONTACT,
        )

        contact = XeroContact(Name="Duplicate")

        async with XeroClient(mock_settings) as client:
            with pytest.raises(XeroAPIError) as exc_info:
                await client.create_contact(contact)

        assert "unique name" in str(exc_info.value).lower()


class TestRateLimiting:
    """Tests for rate limiting behavior."""

    @pytest.mark.asyncio
    async def test_respects_rate_limit_buffer(self, mock_settings, httpx_mock):
        """Test that rate limit buffer is respected."""
        # Set up multiple successful responses
        for _ in range(5):
            httpx_mock.add_response(
                method="GET",
                url__regex=r".*/Contacts.*",
                json=make_xero_contacts_response([]),
                headers={"X-Rate-Limit-Remaining": "59"},
            )

        mock_settings.xero_rate_limit_delay = 0.01

        async with XeroClient(mock_settings) as client:
            for _ in range(3):
                await client.fetch_contacts()

        assert len(httpx_mock.get_requests()) == 3


class TestGetContact:
    """Tests for fetching a single contact."""

    @pytest.mark.asyncio
    async def test_get_contact_success(self, mock_settings, httpx_mock):
        """Test successful single contact fetch."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/Contacts/abc-123.*",
            json={"Contacts": [make_xero_contact(contact_id="abc-123")]},
            headers={"X-Rate-Limit-Remaining": "59"},
        )

        async with XeroClient(mock_settings) as client:
            contact = await client.get_contact("abc-123")

        assert contact is not None
        assert contact.ContactID == "abc-123"

    @pytest.mark.asyncio
    async def test_get_contact_not_found(self, mock_settings, httpx_mock):
        """Test contact not found returns None."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/Contacts/nonexistent.*",
            status_code=404,
            json=XERO_ERROR_NOT_FOUND,
        )

        async with XeroClient(mock_settings) as client:
            contact = await client.get_contact("nonexistent")

        assert contact is None
