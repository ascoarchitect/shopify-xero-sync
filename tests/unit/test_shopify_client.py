"""Unit tests for Shopify API client.

Tests verify that:
- API requests are properly formatted
- Rate limiting is handled correctly
- Authentication errors are detected
- Response parsing works correctly
- Error scenarios are handled gracefully
"""

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from datetime import datetime
import httpx

from src.shopify_client import (
    ShopifyClient,
    ShopifyAPIError,
    ShopifyRateLimitError,
    ShopifyAuthError,
)
from src.config import Settings

from tests.fixtures.shopify_fixtures import (
    make_shopify_customer,
    make_shopify_customers_response,
    make_shopify_product,
    make_shopify_products_response,
    make_shopify_order,
    make_shopify_orders_response,
    SHOPIFY_SHOP_INFO,
    SHOPIFY_ERROR_AUTH,
    SHOPIFY_ERROR_NOT_FOUND,
    SHOPIFY_ERROR_RATE_LIMIT,
)


@pytest.fixture
def mock_settings(mock_env_vars):
    """Create settings with mock environment variables."""
    return Settings()


class TestShopifyClientInit:
    """Tests for ShopifyClient initialization."""

    def test_client_init(self, mock_settings):
        """Test client initializes with correct base URL."""
        client = ShopifyClient(mock_settings)

        assert "test-store.myshopify.com" in client.base_url
        assert "2024-01" in client.base_url

    def test_client_rate_limit_from_settings(self, mock_settings):
        """Test rate limit delay comes from settings."""
        client = ShopifyClient(mock_settings)

        assert client.rate_limit_delay == mock_settings.shopify_rate_limit_delay


class TestShopifyClientContextManager:
    """Tests for async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_creates_client(self, mock_settings):
        """Test context manager creates httpx client."""
        client = ShopifyClient(mock_settings)

        async with client as c:
            assert c._client is not None

    @pytest.mark.asyncio
    async def test_context_manager_closes_client(self, mock_settings):
        """Test context manager closes httpx client on exit."""
        client = ShopifyClient(mock_settings)

        async with client as c:
            assert c._client is not None

        assert client._client is None


class TestFetchCustomers:
    """Tests for fetching customers."""

    @pytest.mark.asyncio
    async def test_fetch_customers_success(self, mock_settings, httpx_mock):
        """Test successful customer fetch."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/customers\.json.*",
            json=make_shopify_customers_response(),
            headers={"X-Shopify-Shop-Api-Call-Limit": "1/40"},
        )

        async with ShopifyClient(mock_settings) as client:
            customers = await client.fetch_customers()

        assert len(customers) == 3
        assert customers[0].first_name == "John"

    @pytest.mark.asyncio
    async def test_fetch_customers_with_since_id(self, mock_settings, httpx_mock):
        """Test fetch customers with since_id parameter."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/customers\.json.*since_id=100.*",
            json=make_shopify_customers_response([
                make_shopify_customer(id=101, email="new@example.com")
            ]),
            headers={"X-Shopify-Shop-Api-Call-Limit": "1/40"},
        )

        async with ShopifyClient(mock_settings) as client:
            customers = await client.fetch_customers(since_id=100)

        assert len(customers) == 1
        assert customers[0].id == 101

    @pytest.mark.asyncio
    async def test_fetch_customers_with_updated_at_min(self, mock_settings, httpx_mock):
        """Test fetch customers with updated_at_min parameter."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/customers\.json.*updated_at_min.*",
            json=make_shopify_customers_response([]),
            headers={"X-Shopify-Shop-Api-Call-Limit": "1/40"},
        )

        async with ShopifyClient(mock_settings) as client:
            customers = await client.fetch_customers(
                updated_at_min=datetime(2024, 1, 1)
            )

        assert len(customers) == 0

    @pytest.mark.asyncio
    async def test_fetch_customers_limit_capped(self, mock_settings, httpx_mock):
        """Test that limit is capped at 250."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/customers\.json.*limit=250.*",
            json=make_shopify_customers_response([]),
            headers={"X-Shopify-Shop-Api-Call-Limit": "1/40"},
        )

        async with ShopifyClient(mock_settings) as client:
            await client.fetch_customers(limit=500)

        # Request should have limit=250
        request = httpx_mock.get_request()
        assert "limit=250" in str(request.url)

    @pytest.mark.asyncio
    async def test_fetch_customers_handles_invalid_data(self, mock_settings, httpx_mock):
        """Test that invalid customer data is skipped."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/customers\.json.*",
            json={"customers": [
                make_shopify_customer(id=1),
                {"invalid": "data"},  # Missing required fields
                make_shopify_customer(id=2),
            ]},
            headers={"X-Shopify-Shop-Api-Call-Limit": "1/40"},
        )

        async with ShopifyClient(mock_settings) as client:
            customers = await client.fetch_customers()

        assert len(customers) == 2


class TestFetchProducts:
    """Tests for fetching products."""

    @pytest.mark.asyncio
    async def test_fetch_products_success(self, mock_settings, httpx_mock):
        """Test successful product fetch."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/products\.json.*",
            json=make_shopify_products_response(),
            headers={"X-Shopify-Shop-Api-Call-Limit": "1/40"},
        )

        async with ShopifyClient(mock_settings) as client:
            products = await client.fetch_products()

        assert len(products) == 3
        assert products[0].title == "Lavender Wax Melt"

    @pytest.mark.asyncio
    async def test_fetch_products_with_pagination(self, mock_settings, httpx_mock):
        """Test fetch products with pagination parameters."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/products\.json.*since_id=50.*",
            json=make_shopify_products_response([
                make_shopify_product(id=51, title="New Product")
            ]),
            headers={"X-Shopify-Shop-Api-Call-Limit": "1/40"},
        )

        async with ShopifyClient(mock_settings) as client:
            products = await client.fetch_products(since_id=50)

        assert len(products) == 1


class TestFetchOrders:
    """Tests for fetching orders."""

    @pytest.mark.asyncio
    async def test_fetch_orders_success(self, mock_settings, httpx_mock):
        """Test successful order fetch."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/orders\.json.*",
            json=make_shopify_orders_response(),
            headers={"X-Shopify-Shop-Api-Call-Limit": "1/40"},
        )

        async with ShopifyClient(mock_settings) as client:
            orders = await client.fetch_orders()

        assert len(orders) == 2

    @pytest.mark.asyncio
    async def test_fetch_orders_with_status_filter(self, mock_settings, httpx_mock):
        """Test fetch orders with status filter."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/orders\.json.*status=open.*",
            json=make_shopify_orders_response([
                make_shopify_order(id=1, financial_status="pending")
            ]),
            headers={"X-Shopify-Shop-Api-Call-Limit": "1/40"},
        )

        async with ShopifyClient(mock_settings) as client:
            orders = await client.fetch_orders(status="open")

        assert len(orders) == 1


class TestGetSingleCustomer:
    """Tests for fetching a single customer."""

    @pytest.mark.asyncio
    async def test_get_customer_success(self, mock_settings, httpx_mock):
        """Test successful single customer fetch."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/customers/123\.json",
            json={"customer": make_shopify_customer(id=123)},
            headers={"X-Shopify-Shop-Api-Call-Limit": "1/40"},
        )

        async with ShopifyClient(mock_settings) as client:
            customer = await client.get_customer(123)

        assert customer is not None
        assert customer.id == 123

    @pytest.mark.asyncio
    async def test_get_customer_not_found(self, mock_settings, httpx_mock):
        """Test customer not found returns None."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/customers/999\.json",
            status_code=404,
            json=SHOPIFY_ERROR_NOT_FOUND,
        )

        async with ShopifyClient(mock_settings) as client:
            customer = await client.get_customer(999)

        assert customer is None


class TestCheckConnection:
    """Tests for connection check."""

    @pytest.mark.asyncio
    async def test_check_connection_success(self, mock_settings, httpx_mock):
        """Test successful connection check."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/shop\.json",
            json=SHOPIFY_SHOP_INFO,
            headers={"X-Shopify-Shop-Api-Call-Limit": "1/40"},
        )

        async with ShopifyClient(mock_settings) as client:
            result = await client.check_connection()

        assert result is True

    @pytest.mark.asyncio
    async def test_check_connection_failure(self, mock_settings, httpx_mock):
        """Test connection check failure."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/shop\.json",
            status_code=401,
            json=SHOPIFY_ERROR_AUTH,
        )

        async with ShopifyClient(mock_settings) as client:
            result = await client.check_connection()

        assert result is False


class TestErrorHandling:
    """Tests for error handling scenarios."""

    @pytest.mark.asyncio
    async def test_auth_error(self, mock_settings, httpx_mock):
        """Test authentication error raises ShopifyAuthError."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/customers\.json.*",
            status_code=401,
            json=SHOPIFY_ERROR_AUTH,
        )

        async with ShopifyClient(mock_settings) as client:
            with pytest.raises(ShopifyAuthError):
                await client.fetch_customers()

    @pytest.mark.asyncio
    async def test_not_found_error(self, mock_settings, httpx_mock):
        """Test 404 raises ShopifyAPIError."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/nonexistent\.json",
            status_code=404,
            json=SHOPIFY_ERROR_NOT_FOUND,
        )

        async with ShopifyClient(mock_settings) as client:
            with pytest.raises(ShopifyAPIError) as exc_info:
                await client._request("GET", "/nonexistent.json")

        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_rate_limit_retry(self, mock_settings, httpx_mock):
        """Test rate limit triggers retry."""
        # First response: rate limit
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/customers\.json.*",
            status_code=429,
            headers={"Retry-After": "0.1"},
        )
        # Second response: success
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/customers\.json.*",
            json=make_shopify_customers_response([]),
            headers={"X-Shopify-Shop-Api-Call-Limit": "1/40"},
        )

        async with ShopifyClient(mock_settings) as client:
            customers = await client.fetch_customers()

        assert len(customers) == 0
        assert len(httpx_mock.get_requests()) == 2

    @pytest.mark.asyncio
    async def test_timeout_retry(self, mock_settings, httpx_mock):
        """Test timeout triggers retry."""
        # First call: timeout
        httpx_mock.add_exception(httpx.TimeoutException("Timeout"))
        # Second call: success
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/customers\.json.*",
            json=make_shopify_customers_response([]),
            headers={"X-Shopify-Shop-Api-Call-Limit": "1/40"},
        )

        async with ShopifyClient(mock_settings) as client:
            customers = await client.fetch_customers()

        assert len(customers) == 0

    @pytest.mark.asyncio
    async def test_request_error_retry(self, mock_settings, httpx_mock):
        """Test network error triggers retry."""
        # First call: network error
        httpx_mock.add_exception(httpx.RequestError("Connection failed"))
        # Second call: success
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/customers\.json.*",
            json=make_shopify_customers_response([]),
            headers={"X-Shopify-Shop-Api-Call-Limit": "1/40"},
        )

        async with ShopifyClient(mock_settings) as client:
            customers = await client.fetch_customers()

        assert len(customers) == 0

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self, mock_settings, httpx_mock):
        """Test error after max retries."""
        # All calls timeout
        for _ in range(3):
            httpx_mock.add_exception(httpx.TimeoutException("Timeout"))

        async with ShopifyClient(mock_settings) as client:
            with pytest.raises(ShopifyAPIError) as exc_info:
                await client.fetch_customers()

        assert "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_client_not_initialized_error(self, mock_settings):
        """Test error when client not initialized."""
        client = ShopifyClient(mock_settings)

        with pytest.raises(ShopifyAPIError) as exc_info:
            await client._request("GET", "/test.json")

        assert "not initialized" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_generic_api_error(self, mock_settings, httpx_mock):
        """Test generic API error handling."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/customers\.json.*",
            status_code=500,
            text="Internal Server Error",
        )

        async with ShopifyClient(mock_settings) as client:
            with pytest.raises(ShopifyAPIError) as exc_info:
                await client.fetch_customers()

        assert "500" in str(exc_info.value)


class TestRateLimiting:
    """Tests for rate limiting behavior."""

    @pytest.mark.asyncio
    async def test_respects_rate_limit_delay(self, mock_settings, httpx_mock):
        """Test that rate limit delay is respected between requests."""
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/customers\.json.*",
            json=make_shopify_customers_response([make_shopify_customer(id=1)]),
            headers={"X-Shopify-Shop-Api-Call-Limit": "1/40"},
        )
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/customers\.json.*",
            json=make_shopify_customers_response([]),
            headers={"X-Shopify-Shop-Api-Call-Limit": "2/40"},
        )

        # Use a very short rate limit for testing
        mock_settings.shopify_rate_limit_delay = 0.01

        async with ShopifyClient(mock_settings) as client:
            await client.fetch_customers()
            await client.fetch_customers()

        assert len(httpx_mock.get_requests()) == 2


class TestPagination:
    """Tests for pagination with fetch_all methods."""

    @pytest.mark.asyncio
    async def test_fetch_all_customers(self, mock_settings, httpx_mock):
        """Test fetching all customers with pagination."""
        # First page
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/customers\.json(?!.*since_id).*",
            json=make_shopify_customers_response([
                make_shopify_customer(id=1),
                make_shopify_customer(id=2),
            ]),
            headers={"X-Shopify-Shop-Api-Call-Limit": "1/40"},
        )
        # Second page (empty - end pagination)
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/customers\.json.*since_id=2.*",
            json=make_shopify_customers_response([]),
            headers={"X-Shopify-Shop-Api-Call-Limit": "2/40"},
        )

        async with ShopifyClient(mock_settings) as client:
            customers = []
            async for customer in client.fetch_all_customers():
                customers.append(customer)

        assert len(customers) == 2

    @pytest.mark.asyncio
    async def test_fetch_all_products(self, mock_settings, httpx_mock):
        """Test fetching all products with pagination."""
        # First page
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/products\.json(?!.*since_id).*",
            json=make_shopify_products_response([
                make_shopify_product(id=1),
            ]),
            headers={"X-Shopify-Shop-Api-Call-Limit": "1/40"},
        )
        # Second page (empty)
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/products\.json.*since_id=1.*",
            json=make_shopify_products_response([]),
            headers={"X-Shopify-Shop-Api-Call-Limit": "2/40"},
        )

        async with ShopifyClient(mock_settings) as client:
            products = []
            async for product in client.fetch_all_products():
                products.append(product)

        assert len(products) == 1

    @pytest.mark.asyncio
    async def test_fetch_all_orders(self, mock_settings, httpx_mock):
        """Test fetching all orders with pagination."""
        # First page
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/orders\.json(?!.*since_id).*",
            json=make_shopify_orders_response([
                make_shopify_order(id=1, order_number=1001),
            ]),
            headers={"X-Shopify-Shop-Api-Call-Limit": "1/40"},
        )
        # Second page (empty)
        httpx_mock.add_response(
            method="GET",
            url__regex=r".*/orders\.json.*since_id=1.*",
            json=make_shopify_orders_response([]),
            headers={"X-Shopify-Shop-Api-Call-Limit": "2/40"},
        )

        async with ShopifyClient(mock_settings) as client:
            orders = []
            async for order in client.fetch_all_orders():
                orders.append(order)

        assert len(orders) == 1
