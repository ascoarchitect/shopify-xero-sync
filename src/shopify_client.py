"""Shopify Admin API client.

Handles authentication, rate limiting, and API operations for
fetching customers, products, and orders from Shopify.
"""

import asyncio
import logging
from typing import List, Optional, AsyncGenerator
from datetime import datetime

import httpx

from .config import Settings
from .models import ShopifyCustomer, ShopifyProduct, ShopifyOrder

logger = logging.getLogger(__name__)


class ShopifyAPIError(Exception):
    """Base exception for Shopify API errors."""
    pass


class ShopifyRateLimitError(ShopifyAPIError):
    """Raised when rate limit is exceeded."""
    def __init__(self, retry_after: float = 2.0):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s")


class ShopifyAuthError(ShopifyAPIError):
    """Raised when authentication fails."""
    pass


class ShopifyClient:
    """Async client for Shopify Admin API."""

    # Shopify REST Admin API version
    API_VERSION = "2024-01"

    # Rate limit: 2 calls per second (bucket of 40)
    DEFAULT_RATE_LIMIT_DELAY = 0.5

    def __init__(self, settings: Settings):
        """Initialize Shopify client.

        Args:
            settings: Application settings with Shopify credentials
        """
        self.settings = settings
        self.base_url = f"{settings.shopify_shop_url}/admin/api/{self.API_VERSION}"
        self.rate_limit_delay = settings.shopify_rate_limit_delay
        self._last_request_time: Optional[float] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._access_token: Optional[str] = settings.shopify_access_token

    def set_access_token(self, token: str) -> None:
        """Set or update the access token.

        Args:
            token: Shopify access token
        """
        self._access_token = token
        if self._client:
            self._client.headers["X-Shopify-Access-Token"] = token

    async def __aenter__(self) -> "ShopifyClient":
        """Async context manager entry."""
        if not self._access_token:
            raise ShopifyAuthError(
                "No access token available. Run 'python auth_shopify.py' to authenticate."
            )
        
        self._client = httpx.AsyncClient(
            headers={
                "X-Shopify-Access-Token": self._access_token,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _respect_rate_limit(self) -> None:
        """Ensure we don't exceed rate limits.

        Adds delay between requests to stay under 2 calls/second.
        """
        if self._last_request_time is not None:
            elapsed = asyncio.get_event_loop().time() - self._last_request_time
            if elapsed < self.rate_limit_delay:
                await asyncio.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
        retries: int = 3,
    ) -> dict:
        """Make an API request with rate limiting and retries.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., "/customers.json")
            params: Query parameters
            json_data: JSON body for POST/PUT
            retries: Number of retry attempts

        Returns:
            JSON response as dictionary

        Raises:
            ShopifyAPIError: On API errors
            ShopifyAuthError: On authentication failures
            ShopifyRateLimitError: On rate limit (after retries exhausted)
        """
        if not self._client:
            raise ShopifyAPIError("Client not initialized. Use async context manager.")

        url = f"{self.base_url}{endpoint}"

        for attempt in range(retries):
            await self._respect_rate_limit()

            try:
                response = await self._client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                )

                # Log rate limit info from headers
                call_limit = response.headers.get("X-Shopify-Shop-Api-Call-Limit", "unknown")
                logger.debug(f"Shopify API call: {method} {endpoint} (limit: {call_limit})")

                # Handle responses
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 201:
                    return response.json()
                elif response.status_code == 401:
                    raise ShopifyAuthError("Invalid access token")
                elif response.status_code == 429:
                    # Rate limit exceeded
                    retry_after = float(response.headers.get("Retry-After", "2.0"))
                    logger.warning(f"Rate limit hit, waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                    continue
                elif response.status_code == 404:
                    raise ShopifyAPIError(f"Resource not found: {endpoint}")
                else:
                    error_body = response.text
                    raise ShopifyAPIError(
                        f"API error {response.status_code}: {error_body}"
                    )

            except httpx.TimeoutException:
                logger.warning(f"Request timeout (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise ShopifyAPIError(f"Request timeout after {retries} attempts")

            except httpx.RequestError as e:
                logger.warning(f"Request error (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ShopifyAPIError(f"Request failed: {e}")

        raise ShopifyRateLimitError()

    # =========================================================================
    # CUSTOMERS
    # =========================================================================

    async def fetch_customers(
        self,
        since_id: Optional[int] = None,
        updated_at_min: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[ShopifyCustomer]:
        """Fetch customers from Shopify.

        Args:
            since_id: Only fetch customers after this ID
            updated_at_min: Only fetch customers updated after this time
            limit: Maximum customers per request (max 250)

        Returns:
            List of ShopifyCustomer objects
        """
        params = {"limit": min(limit, 250)}
        if since_id:
            params["since_id"] = since_id
        if updated_at_min:
            params["updated_at_min"] = updated_at_min.isoformat()

        response = await self._request("GET", "/customers.json", params=params)

        customers = []
        for customer_data in response.get("customers", []):
            try:
                customers.append(ShopifyCustomer.model_validate(customer_data))
            except Exception as e:
                logger.error(f"Failed to parse customer {customer_data.get('id')}: {e}")
                continue

        logger.info(f"Fetched {len(customers)} customers from Shopify")
        return customers

    async def fetch_all_customers(
        self,
        updated_at_min: Optional[datetime] = None,
    ) -> AsyncGenerator[ShopifyCustomer, None]:
        """Fetch all customers with pagination.

        Args:
            updated_at_min: Only fetch customers updated after this time

        Yields:
            ShopifyCustomer objects
        """
        since_id = None
        while True:
            customers = await self.fetch_customers(
                since_id=since_id,
                updated_at_min=updated_at_min,
                limit=250,
            )
            if not customers:
                break

            for customer in customers:
                yield customer

            since_id = customers[-1].id

    async def get_customer(self, customer_id: int) -> Optional[ShopifyCustomer]:
        """Fetch a single customer by ID.

        Args:
            customer_id: Shopify customer ID

        Returns:
            ShopifyCustomer or None if not found
        """
        try:
            response = await self._request("GET", f"/customers/{customer_id}.json")
            return ShopifyCustomer.model_validate(response.get("customer", {}))
        except ShopifyAPIError as e:
            if "not found" in str(e).lower():
                return None
            raise

    # =========================================================================
    # PRODUCTS
    # =========================================================================

    async def fetch_products(
        self,
        since_id: Optional[int] = None,
        updated_at_min: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[ShopifyProduct]:
        """Fetch products from Shopify.

        Args:
            since_id: Only fetch products after this ID
            updated_at_min: Only fetch products updated after this time
            limit: Maximum products per request (max 250)

        Returns:
            List of ShopifyProduct objects
        """
        params = {"limit": min(limit, 250)}
        if since_id:
            params["since_id"] = since_id
        if updated_at_min:
            params["updated_at_min"] = updated_at_min.isoformat()

        response = await self._request("GET", "/products.json", params=params)

        products = []
        for product_data in response.get("products", []):
            try:
                products.append(ShopifyProduct.model_validate(product_data))
            except Exception as e:
                logger.error(f"Failed to parse product {product_data.get('id')}: {e}")
                continue

        logger.info(f"Fetched {len(products)} products from Shopify")
        return products

    async def fetch_all_products(
        self,
        updated_at_min: Optional[datetime] = None,
    ) -> AsyncGenerator[ShopifyProduct, None]:
        """Fetch all products with pagination.

        Args:
            updated_at_min: Only fetch products updated after this time

        Yields:
            ShopifyProduct objects
        """
        since_id = None
        while True:
            products = await self.fetch_products(
                since_id=since_id,
                updated_at_min=updated_at_min,
                limit=250,
            )
            if not products:
                break

            for product in products:
                yield product

            since_id = products[-1].id

    # =========================================================================
    # ORDERS
    # =========================================================================

    async def fetch_orders(
        self,
        since_id: Optional[int] = None,
        updated_at_min: Optional[datetime] = None,
        status: str = "any",
        limit: int = 50,
    ) -> List[ShopifyOrder]:
        """Fetch orders from Shopify.

        Args:
            since_id: Only fetch orders after this ID
            updated_at_min: Only fetch orders updated after this time
            status: Order status filter (any, open, closed, cancelled)
            limit: Maximum orders per request (max 250)

        Returns:
            List of ShopifyOrder objects
        """
        params = {"limit": min(limit, 250), "status": status}
        if since_id:
            params["since_id"] = since_id
        if updated_at_min:
            params["updated_at_min"] = updated_at_min.isoformat()

        response = await self._request("GET", "/orders.json", params=params)

        orders = []
        for order_data in response.get("orders", []):
            try:
                orders.append(ShopifyOrder.model_validate(order_data))
            except Exception as e:
                logger.error(f"Failed to parse order {order_data.get('id')}: {e}")
                continue

        logger.info(f"Fetched {len(orders)} orders from Shopify")
        return orders

    async def fetch_all_orders(
        self,
        updated_at_min: Optional[datetime] = None,
        status: str = "any",
    ) -> AsyncGenerator[ShopifyOrder, None]:
        """Fetch all orders with pagination.

        Args:
            updated_at_min: Only fetch orders updated after this time
            status: Order status filter

        Yields:
            ShopifyOrder objects
        """
        since_id = None
        while True:
            orders = await self.fetch_orders(
                since_id=since_id,
                updated_at_min=updated_at_min,
                status=status,
                limit=250,
            )
            if not orders:
                break

            for order in orders:
                yield order

            since_id = orders[-1].id

    # =========================================================================
    # HEALTH CHECK
    # =========================================================================

    async def check_connection(self) -> bool:
        """Verify API connection is working.

        Returns:
            True if connection is successful
        """
        try:
            await self._request("GET", "/shop.json")
            logger.info("Shopify API connection successful")
            return True
        except Exception as e:
            logger.error(f"Shopify API connection failed: {e}")
            return False
