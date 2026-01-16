"""Shopify OAuth2 authentication flow.

Handles the authorization code grant flow for Shopify apps created
in the Dev Dashboard. This replaces the legacy custom app access tokens.
"""

import asyncio
import hashlib
import logging
import secrets
import webbrowser
from typing import Optional, Tuple
from urllib.parse import urlencode, parse_qs, urlparse

import httpx
from aiohttp import web

logger = logging.getLogger(__name__)


class ShopifyOAuth:
    """Handles Shopify OAuth2 authorization code grant flow."""

    OAUTH_AUTHORIZE_URL = "https://{shop}/admin/oauth/authorize"
    OAUTH_TOKEN_URL = "https://{shop}/admin/oauth/access_token"
    
    # Required scopes for this integration
    REQUIRED_SCOPES = [
        "read_customers",
        "read_products", 
        "read_orders",
    ]

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        shop_url: str,
        redirect_uri: str = "http://localhost:8080/callback",
    ):
        """Initialize OAuth handler.

        Args:
            client_id: Shopify app client ID
            client_secret: Shopify app client secret
            shop_url: Shop URL (e.g., https://store.myshopify.com)
            redirect_uri: OAuth callback URL
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.shop_url = shop_url.rstrip("/")
        self.redirect_uri = redirect_uri
        
        # Extract shop domain
        self.shop = shop_url.replace("https://", "").replace("http://", "")
        
        # OAuth state for CSRF protection
        self.state: Optional[str] = None
        self.access_token: Optional[str] = None

    def generate_authorization_url(self) -> str:
        """Generate the OAuth authorization URL.

        Returns:
            URL to redirect user to for authorization
        """
        # Generate random state for CSRF protection
        self.state = secrets.token_urlsafe(32)
        
        params = {
            "client_id": self.client_id,
            "scope": ",".join(self.REQUIRED_SCOPES),
            "redirect_uri": self.redirect_uri,
            "state": self.state,
            "grant_options[]": "offline",  # Request offline (non-expiring) token
        }
        
        url = self.OAUTH_AUTHORIZE_URL.format(shop=self.shop)
        return f"{url}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> str:
        """Exchange authorization code for access token.

        Args:
            code: Authorization code from callback

        Returns:
            Access token

        Raises:
            Exception: If token exchange fails
        """
        url = self.OAUTH_TOKEN_URL.format(shop=self.shop)
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=data, timeout=30)
            
            if response.status_code != 200:
                raise Exception(
                    f"Token exchange failed: {response.status_code} - {response.text}"
                )
            
            result = response.json()
            self.access_token = result.get("access_token")
            
            if not self.access_token:
                raise Exception("No access token in response")
            
            logger.info(f"Successfully obtained access token (scopes: {result.get('scope')})")
            return self.access_token

    async def run_oauth_flow(self) -> str:
        """Run the complete OAuth flow with local callback server.

        This will:
        1. Start a local web server on port 8080
        2. Open browser to authorization URL
        3. Wait for callback with authorization code
        4. Exchange code for access token
        5. Return the access token

        Returns:
            Access token

        Raises:
            Exception: If OAuth flow fails
        """
        # Store the authorization code when received
        auth_code: Optional[str] = None
        auth_state: Optional[str] = None
        error_message: Optional[str] = None
        
        async def callback_handler(request: web.Request) -> web.Response:
            """Handle OAuth callback."""
            nonlocal auth_code, auth_state, error_message
            
            # Check for errors
            if "error" in request.query:
                error_message = request.query.get("error_description", request.query["error"])
                return web.Response(
                    text=f"""
                    <html>
                        <body>
                            <h1>Authorization Failed</h1>
                            <p>{error_message}</p>
                            <p>You can close this window.</p>
                        </body>
                    </html>
                    """,
                    content_type="text/html",
                    status=400,
                )
            
            # Get code and state
            auth_code = request.query.get("code")
            auth_state = request.query.get("state")
            
            if not auth_code:
                return web.Response(
                    text="Missing authorization code",
                    status=400,
                )
            
            return web.Response(
                text="""
                <html>
                    <body>
                        <h1>Authorization Successful!</h1>
                        <p>You can close this window and return to the terminal.</p>
                        <script>window.close();</script>
                    </body>
                </html>
                """,
                content_type="text/html",
            )
        
        # Create web app
        app = web.Application()
        app.router.add_get("/callback", callback_handler)
        
        # Start server
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", 8080)
        await site.start()
        
        logger.info("Started OAuth callback server on http://localhost:8080")
        
        try:
            # Generate and open authorization URL
            auth_url = self.generate_authorization_url()
            logger.info(f"Opening browser for authorization...")
            logger.info(f"If browser doesn't open, visit: {auth_url}")
            
            webbrowser.open(auth_url)
            
            # Wait for callback (with timeout)
            timeout = 300  # 5 minutes
            for _ in range(timeout):
                if auth_code or error_message:
                    break
                await asyncio.sleep(1)
            else:
                raise Exception("OAuth flow timed out after 5 minutes")
            
            if error_message:
                raise Exception(f"Authorization failed: {error_message}")
            
            if not auth_code:
                raise Exception("No authorization code received")
            
            # Verify state to prevent CSRF
            if auth_state != self.state:
                raise Exception("State mismatch - possible CSRF attack")
            
            logger.info("Authorization code received, exchanging for token...")
            
            # Exchange code for token
            access_token = await self.exchange_code_for_token(auth_code)
            
            return access_token
            
        finally:
            # Clean up server
            await runner.cleanup()
            logger.info("OAuth callback server stopped")


async def get_access_token_interactive(
    client_id: str,
    client_secret: str,
    shop_url: str,
) -> str:
    """Run interactive OAuth flow to get access token.

    Args:
        client_id: Shopify app client ID
        client_secret: Shopify app client secret
        shop_url: Shop URL

    Returns:
        Access token
    """
    oauth = ShopifyOAuth(client_id, client_secret, shop_url)
    return await oauth.run_oauth_flow()
