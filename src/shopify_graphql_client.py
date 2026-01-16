"""Shopify GraphQL Admin API client.

Provides efficient bulk data fetching using GraphQL queries.
Significantly faster than REST API for large datasets.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List, AsyncGenerator, Dict, Any
import httpx

from .config import Settings
from .models import ShopifyCustomer, ShopifyProduct, ShopifyOrder, ShopifyAddress, ShopifyProductVariant, ShopifyLineItem

logger = logging.getLogger(__name__)


class ShopifyGraphQLError(Exception):
    """Base exception for Shopify GraphQL API errors."""
    pass


class ShopifyGraphQLClient:
    """Shopify GraphQL Admin API client with bulk operations."""

    API_VERSION = "2024-01"
    GRAPHQL_ENDPOINT = "/admin/api/{version}/graphql.json"
    
    # GraphQL has different rate limits - cost-based
    DEFAULT_RATE_LIMIT_DELAY = 0.5

    def __init__(self, settings: Settings):
        """Initialize GraphQL client.

        Args:
            settings: Application settings with Shopify credentials
        """
        self.settings = settings
        self.shop_url = settings.shopify_shop_url
        self.access_token = settings.shopify_access_token
        self.graphql_url = f"{self.shop_url}{self.GRAPHQL_ENDPOINT.format(version=self.API_VERSION)}"
        self.rate_limit_delay = settings.shopify_rate_limit_delay
        self._last_request_time: Optional[float] = None
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _respect_rate_limit(self) -> None:
        """Ensure we don't exceed rate limits."""
        if self._last_request_time is not None:
            elapsed = asyncio.get_event_loop().time() - self._last_request_time
            if elapsed < self.rate_limit_delay:
                await asyncio.sleep(self.rate_limit_delay - elapsed)
        
        self._last_request_time = asyncio.get_event_loop().time()

    async def _query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a GraphQL query.

        Args:
            query: GraphQL query string
            variables: Optional query variables

        Returns:
            Response data dictionary

        Raises:
            ShopifyGraphQLError: On API errors
        """
        if not self._client:
            raise ShopifyGraphQLError("Client not initialized. Use async context manager.")

        await self._respect_rate_limit()

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            response = await self._client.post(
                self.graphql_url,
                json=payload,
                headers={
                    "X-Shopify-Access-Token": self.access_token,
                    "Content-Type": "application/json",
                },
            )

            # Log throttle status
            throttle_status = response.headers.get("X-Shopify-Shop-Api-Call-Limit", "unknown")
            logger.debug(f"GraphQL query executed (throttle: {throttle_status})")

            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", "2.0"))
                logger.warning(f"Rate limit hit, waiting {retry_after}s")
                await asyncio.sleep(retry_after)
                # Retry once
                return await self._query(query, variables)

            response.raise_for_status()
            data = response.json()

            # Check for GraphQL errors
            if "errors" in data:
                errors = data["errors"]
                error_messages = [e.get("message", str(e)) for e in errors]
                raise ShopifyGraphQLError(f"GraphQL errors: {', '.join(error_messages)}")

            return data.get("data", {})

        except httpx.HTTPError as e:
            raise ShopifyGraphQLError(f"HTTP error: {e}")

    # =========================================================================
    # CUSTOMERS
    # =========================================================================

    async def fetch_all_customers(
        self,
        updated_at_min: Optional[datetime] = None,
        batch_size: int = 250,
    ) -> List[ShopifyCustomer]:
        """Fetch all customers using GraphQL bulk query.

        Args:
            updated_at_min: Only fetch customers updated after this time
            batch_size: Number of customers per page

        Returns:
            List of all ShopifyCustomer objects
        """
        customers = []
        cursor = None
        has_next_page = True

        # Build query filter
        query_filter = ""
        if updated_at_min:
            # Format: 2024-01-15T12:00:00Z
            date_str = updated_at_min.strftime("%Y-%m-%dT%H:%M:%SZ")
            query_filter = f'updated_at:>="{date_str}"'

        logger.info(f"Fetching customers from Shopify GraphQL (filter: {query_filter or 'none'})")

        while has_next_page:
            query = """
            query($first: Int!, $after: String, $query: String) {
              customers(first: $first, after: $after, query: $query) {
                edges {
                  node {
                    id
                    email
                    firstName
                    lastName
                    phone
                    createdAt
                    updatedAt
                    note
                    tags
                    taxExempt
                    verifiedEmail
                    defaultAddress {
                      id
                      address1
                      address2
                      city
                      province
                      provinceCode
                      country
                      countryCode
                      zip
                      phone
                      company
                    }
                    addresses {
                      id
                      address1
                      address2
                      city
                      province
                      provinceCode
                      country
                      countryCode
                      zip
                      phone
                      company
                    }
                  }
                }
                pageInfo {
                  hasNextPage
                  endCursor
                }
              }
            }
            """

            variables = {
                "first": batch_size,
                "after": cursor,
                "query": query_filter if query_filter else None,
            }

            data = await self._query(query, variables)
            
            customer_data = data.get("customers", {})
            edges = customer_data.get("edges", [])
            page_info = customer_data.get("pageInfo", {})

            # Convert GraphQL response to our models
            for edge in edges:
                node = edge.get("node", {})
                try:
                    customer = self._parse_customer(node)
                    customers.append(customer)
                except Exception as e:
                    logger.error(f"Failed to parse customer {node.get('id')}: {e}")

            logger.info(f"Fetched {len(edges)} customers from Shopify")

            has_next_page = page_info.get("hasNextPage", False)
            cursor = page_info.get("endCursor")

        logger.info(f"Total customers fetched: {len(customers)}")
        return customers

    def _parse_customer(self, node: Dict[str, Any]) -> ShopifyCustomer:
        """Parse GraphQL customer node to ShopifyCustomer model."""
        # Extract numeric ID from GraphQL global ID (gid://shopify/Customer/123456)
        gid = node.get("id", "")
        customer_id = int(gid.split("/")[-1]) if "/" in gid else 0

        # Parse default address
        default_address = None
        if node.get("defaultAddress"):
            default_address = self._parse_address(node["defaultAddress"])

        # Parse all addresses
        addresses = []
        for addr in node.get("addresses", []):
            addresses.append(self._parse_address(addr))

        # Convert tags from list to comma-separated string (to match REST API format)
        tags = node.get("tags")
        if isinstance(tags, list):
            tags = ", ".join(tags) if tags else None

        return ShopifyCustomer(
            id=customer_id,
            email=node.get("email"),
            first_name=node.get("firstName"),
            last_name=node.get("lastName"),
            phone=node.get("phone"),
            created_at=node.get("createdAt"),
            updated_at=node.get("updatedAt"),
            default_address=default_address,
            addresses=addresses,
            note=node.get("note"),
            tags=tags,
            tax_exempt=node.get("taxExempt", False),
            verified_email=node.get("verifiedEmail", False),
        )

    def _parse_address(self, addr: Dict[str, Any]) -> ShopifyAddress:
        """Parse GraphQL address to ShopifyAddress model."""
        # Extract numeric ID - handle query parameters in GID
        gid = addr.get("id", "")
        addr_id = None
        if "/" in gid:
            # Extract ID and remove query parameters
            id_part = gid.split("/")[-1].split("?")[0]
            try:
                addr_id = int(id_part)
            except ValueError:
                addr_id = None

        return ShopifyAddress(
            id=addr_id,
            address1=addr.get("address1"),
            address2=addr.get("address2"),
            city=addr.get("city"),
            province=addr.get("province"),
            province_code=addr.get("provinceCode"),
            country=addr.get("country"),
            country_code=addr.get("countryCode"),
            zip=addr.get("zip"),
            phone=addr.get("phone"),
            company=addr.get("company"),
        )

    # =========================================================================
    # PRODUCTS
    # =========================================================================

    async def fetch_all_products(
        self,
        updated_at_min: Optional[datetime] = None,
        batch_size: int = 250,
    ) -> List[ShopifyProduct]:
        """Fetch all products using GraphQL bulk query.

        Args:
            updated_at_min: Only fetch products updated after this time
            batch_size: Number of products per page

        Returns:
            List of all ShopifyProduct objects
        """
        products = []
        cursor = None
        has_next_page = True

        # Build query filter
        query_filter = ""
        if updated_at_min:
            date_str = updated_at_min.strftime("%Y-%m-%dT%H:%M:%SZ")
            query_filter = f'updated_at:>="{date_str}"'

        logger.info(f"Fetching products from Shopify GraphQL (filter: {query_filter or 'none'})")

        while has_next_page:
            query = """
            query($first: Int!, $after: String, $query: String) {
              products(first: $first, after: $after, query: $query) {
                edges {
                  node {
                    id
                    title
                    descriptionHtml
                    vendor
                    productType
                    createdAt
                    updatedAt
                    publishedAt
                    status
                    tags
                    variants(first: 100) {
                      edges {
                        node {
                          id
                          title
                          sku
                          price
                          inventoryQuantity
                        }
                      }
                    }
                  }
                }
                pageInfo {
                  hasNextPage
                  endCursor
                }
              }
            }
            """

            variables = {
                "first": batch_size,
                "after": cursor,
                "query": query_filter if query_filter else None,
            }

            data = await self._query(query, variables)
            
            product_data = data.get("products", {})
            edges = product_data.get("edges", [])
            page_info = product_data.get("pageInfo", {})

            # Convert GraphQL response to our models
            for edge in edges:
                node = edge.get("node", {})
                try:
                    product = self._parse_product(node)
                    products.append(product)
                except Exception as e:
                    logger.error(f"Failed to parse product {node.get('id')}: {e}")

            logger.info(f"Fetched {len(edges)} products from Shopify")

            has_next_page = page_info.get("hasNextPage", False)
            cursor = page_info.get("endCursor")

        logger.info(f"Total products fetched: {len(products)}")
        return products

    def _parse_product(self, node: Dict[str, Any]) -> ShopifyProduct:
        """Parse GraphQL product node to ShopifyProduct model."""
        # Extract numeric ID
        gid = node.get("id", "")
        product_id = int(gid.split("/")[-1]) if "/" in gid else 0

        # Parse variants
        variants = []
        variant_edges = node.get("variants", {}).get("edges", [])
        for edge in variant_edges:
            variant_node = edge.get("node", {})
            variant_gid = variant_node.get("id", "")
            variant_id = int(variant_gid.split("/")[-1]) if "/" in variant_gid else 0

            variants.append(ShopifyProductVariant(
                id=variant_id,
                product_id=product_id,
                title=variant_node.get("title"),
                sku=variant_node.get("sku"),
                price=variant_node.get("price", "0.00"),
                inventory_quantity=variant_node.get("inventoryQuantity", 0),
            ))

        # Convert tags from list to comma-separated string
        tags = node.get("tags")
        if isinstance(tags, list):
            tags = ", ".join(tags) if tags else None

        return ShopifyProduct(
            id=product_id,
            title=node.get("title", ""),
            body_html=node.get("descriptionHtml"),
            vendor=node.get("vendor"),
            product_type=node.get("productType"),
            created_at=node.get("createdAt"),
            updated_at=node.get("updatedAt"),
            published_at=node.get("publishedAt"),
            status=node.get("status", "active").lower(),
            tags=tags,
            variants=variants,
        )

    # =========================================================================
    # ORDERS
    # =========================================================================

    async def fetch_all_orders(
        self,
        updated_at_min: Optional[datetime] = None,
        status: str = "any",
        batch_size: int = 250,
    ) -> List[ShopifyOrder]:
        """Fetch all orders using GraphQL bulk query.

        Args:
            updated_at_min: Only fetch orders updated after this time
            status: Order status filter (any, open, closed, cancelled)
            batch_size: Number of orders per page

        Returns:
            List of all ShopifyOrder objects
        """
        orders = []
        cursor = None
        has_next_page = True

        # Build query filter
        query_parts = []
        if updated_at_min:
            date_str = updated_at_min.strftime("%Y-%m-%dT%H:%M:%SZ")
            query_parts.append(f'updated_at:>="{date_str}"')
        
        if status != "any":
            query_parts.append(f'status:{status}')
        
        query_filter = " AND ".join(query_parts) if query_parts else ""

        logger.info(f"Fetching orders from Shopify GraphQL (filter: {query_filter or 'none'})")

        while has_next_page:
            query = """
            query($first: Int!, $after: String, $query: String) {
              orders(first: $first, after: $after, query: $query) {
                edges {
                  node {
                    id
                    name
                    email
                    createdAt
                    updatedAt
                    processedAt
                    currencyCode
                    totalPriceSet {
                      shopMoney {
                        amount
                      }
                    }
                    subtotalPriceSet {
                      shopMoney {
                        amount
                      }
                    }
                    totalTaxSet {
                      shopMoney {
                        amount
                      }
                    }
                    totalDiscountsSet {
                      shopMoney {
                        amount
                      }
                    }
                    displayFinancialStatus
                    displayFulfillmentStatus
                    note
                    tags
                    customer {
                      id
                      email
                      firstName
                      lastName
                    }
                    lineItems(first: 100) {
                      edges {
                        node {
                          id
                          title
                          quantity
                          variant {
                            id
                            sku
                          }
                          product {
                            id
                          }
                          originalUnitPriceSet {
                            shopMoney {
                              amount
                            }
                          }
                          discountedUnitPriceSet {
                            shopMoney {
                              amount
                            }
                          }
                        }
                      }
                    }
                    billingAddress {
                      address1
                      address2
                      city
                      province
                      provinceCode
                      country
                      countryCode
                      zip
                      phone
                      company
                    }
                    shippingAddress {
                      address1
                      address2
                      city
                      province
                      provinceCode
                      country
                      countryCode
                      zip
                      phone
                      company
                    }
                  }
                }
                pageInfo {
                  hasNextPage
                  endCursor
                }
              }
            }
            """

            variables = {
                "first": batch_size,
                "after": cursor,
                "query": query_filter if query_filter else None,
            }

            data = await self._query(query, variables)
            
            order_data = data.get("orders", {})
            edges = order_data.get("edges", [])
            page_info = order_data.get("pageInfo", {})

            # Convert GraphQL response to our models
            for edge in edges:
                node = edge.get("node", {})
                try:
                    order = self._parse_order(node)
                    orders.append(order)
                except Exception as e:
                    logger.error(f"Failed to parse order {node.get('id')}: {e}")

            logger.info(f"Fetched {len(edges)} orders from Shopify")

            has_next_page = page_info.get("hasNextPage", False)
            cursor = page_info.get("endCursor")

        logger.info(f"Total orders fetched: {len(orders)}")
        return orders

    def _parse_order(self, node: Dict[str, Any]) -> ShopifyOrder:
        """Parse GraphQL order node to ShopifyOrder model."""
        # Extract numeric ID
        gid = node.get("id", "")
        order_id = int(gid.split("/")[-1]) if "/" in gid else 0
        
        # Extract order number from name (e.g., "#1001" -> 1001)
        name = node.get("name", "#0")
        order_number = int(name.replace("#", "")) if name else 0

        # Parse customer
        customer = None
        if node.get("customer"):
            cust = node["customer"]
            cust_gid = cust.get("id", "")
            cust_id = int(cust_gid.split("/")[-1]) if "/" in cust_gid else 0
            customer = ShopifyCustomer(
                id=cust_id,
                email=cust.get("email"),
                first_name=cust.get("firstName"),
                last_name=cust.get("lastName"),
            )

        # Parse line items
        line_items = []
        for edge in node.get("lineItems", {}).get("edges", []):
            item_node = edge.get("node", {})
            item_gid = item_node.get("id", "")
            item_id = int(item_gid.split("/")[-1]) if "/" in item_gid else 0

            variant_id = None
            sku = None
            if item_node.get("variant"):
                var_gid = item_node["variant"].get("id", "")
                variant_id = int(var_gid.split("/")[-1]) if "/" in var_gid else None
                sku = item_node["variant"].get("sku")

            product_id = None
            if item_node.get("product"):
                prod_gid = item_node["product"].get("id", "")
                product_id = int(prod_gid.split("/")[-1]) if "/" in prod_gid else None

            price = item_node.get("discountedUnitPriceSet", {}).get("shopMoney", {}).get("amount", "0.00")

            line_items.append(ShopifyLineItem(
                id=item_id,
                variant_id=variant_id,
                product_id=product_id,
                title=item_node.get("title", ""),
                quantity=item_node.get("quantity", 1),
                sku=sku,
                price=price,
            ))

        # Parse addresses
        billing_address = None
        if node.get("billingAddress"):
            billing_address = ShopifyAddress(**node["billingAddress"])

        shipping_address = None
        if node.get("shippingAddress"):
            shipping_address = ShopifyAddress(**node["shippingAddress"])

        # Convert tags from list to comma-separated string
        tags = node.get("tags")
        if isinstance(tags, list):
            tags = ", ".join(tags) if tags else None

        return ShopifyOrder(
            id=order_id,
            order_number=order_number,
            name=name,
            email=node.get("email"),
            created_at=node.get("createdAt"),
            updated_at=node.get("updatedAt"),
            processed_at=node.get("processedAt"),
            currency=node.get("currencyCode", "GBP"),
            total_price=node.get("totalPriceSet", {}).get("shopMoney", {}).get("amount", "0.00"),
            subtotal_price=node.get("subtotalPriceSet", {}).get("shopMoney", {}).get("amount", "0.00"),
            total_tax=node.get("totalTaxSet", {}).get("shopMoney", {}).get("amount", "0.00"),
            total_discounts=node.get("totalDiscountsSet", {}).get("shopMoney", {}).get("amount", "0.00"),
            financial_status=node.get("displayFinancialStatus"),
            fulfillment_status=node.get("displayFulfillmentStatus"),
            customer=customer,
            line_items=line_items,
            billing_address=billing_address,
            shipping_address=shipping_address,
            note=node.get("note"),
            tags=tags,
        )

    # =========================================================================
    # CONNECTION TEST
    # =========================================================================

    async def check_connection(self) -> bool:
        """Verify API connection is working.

        Returns:
            True if connection is successful
        """
        try:
            query = """
            {
              shop {
                name
                email
              }
            }
            """
            data = await self._query(query)
            shop = data.get("shop", {})
            if shop.get("name"):
                logger.info(f"Shopify GraphQL API connection successful: {shop['name']}")
                return True
            return False
        except Exception as e:
            logger.error(f"Shopify GraphQL API connection failed: {e}")
            return False
