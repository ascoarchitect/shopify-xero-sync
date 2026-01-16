#!/usr/bin/env python3
"""Xero OAuth2 Authorization Helper.

This script handles the one-time OAuth2 authorization flow to get
access and refresh tokens for the Xero API.

Usage:
    1. Set XERO_CLIENT_ID and XERO_CLIENT_SECRET in your .env file
    2. Run: python auth_xero.py
    3. Your browser will open to authorize with Xero
    4. After authorizing, tokens will be saved to your .env file

Requirements:
    pip install httpx python-dotenv
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import socketserver
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

try:
    import httpx
except ImportError:
    print("Error: httpx not installed. Run: pip install httpx")
    sys.exit(1)

try:
    from dotenv import load_dotenv, set_key
except ImportError:
    print("Error: python-dotenv not installed. Run: pip install python-dotenv")
    sys.exit(1)


# Configuration
CALLBACK_PORT = 8080
CALLBACK_PATH = "/callback"
XERO_AUTH_URL = "https://login.xero.com/identity/connect/authorize"
XERO_TOKEN_URL = "https://identity.xero.com/connect/token"
XERO_CONNECTIONS_URL = "https://api.xero.com/connections"

# Scopes needed for sync
SCOPES = [
    "openid",
    "profile",
    "email",
    "accounting.transactions",
    "accounting.contacts",
    "accounting.settings",
    "offline_access",  # Required for refresh tokens
]


class AuthorizationHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler to capture OAuth2 callback."""

    authorization_code = None
    state_received = None
    error = None

    def do_GET(self):
        """Handle GET request from OAuth2 callback."""
        parsed = urlparse(self.path)

        if parsed.path == CALLBACK_PATH:
            query_params = parse_qs(parsed.query)

            if "error" in query_params:
                AuthorizationHandler.error = query_params.get("error_description", ["Unknown error"])[0]
                self._send_error_response()
            elif "code" in query_params:
                AuthorizationHandler.authorization_code = query_params["code"][0]
                AuthorizationHandler.state_received = query_params.get("state", [None])[0]
                self._send_success_response()
            else:
                AuthorizationHandler.error = "No authorization code received"
                self._send_error_response()
        else:
            self.send_response(404)
            self.end_headers()

    def _send_success_response(self):
        """Send success HTML response."""
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authorization Successful</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                       display: flex; justify-content: center; align-items: center;
                       height: 100vh; margin: 0; background: #f5f5f5; }
                .container { text-align: center; padding: 40px; background: white;
                            border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                .success { color: #22c55e; font-size: 48px; margin-bottom: 20px; }
                h1 { color: #333; margin-bottom: 10px; }
                p { color: #666; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success">✓</div>
                <h1>Authorization Successful!</h1>
                <p>You can close this window and return to the terminal.</p>
            </div>
        </body>
        </html>
        """
        self.wfile.write(html.encode())

    def _send_error_response(self):
        """Send error HTML response."""
        self.send_response(400)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authorization Failed</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                       display: flex; justify-content: center; align-items: center;
                       height: 100vh; margin: 0; background: #f5f5f5; }}
                .container {{ text-align: center; padding: 40px; background: white;
                            border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .error {{ color: #ef4444; font-size: 48px; margin-bottom: 20px; }}
                h1 {{ color: #333; margin-bottom: 10px; }}
                p {{ color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="error">✗</div>
                <h1>Authorization Failed</h1>
                <p>{AuthorizationHandler.error}</p>
            </div>
        </body>
        </html>
        """
        self.wfile.write(html.encode())

    def log_message(self, format, *args):
        """Suppress HTTP server logs."""
        pass


def generate_pkce():
    """Generate PKCE code verifier and challenge.

    Returns:
        Tuple of (code_verifier, code_challenge)
    """
    # Generate random code verifier
    code_verifier = secrets.token_urlsafe(32)

    # Create code challenge (SHA256 hash, base64url encoded)
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")

    return code_verifier, code_challenge


def build_authorization_url(client_id: str, redirect_uri: str, state: str, code_challenge: str) -> str:
    """Build the Xero authorization URL.

    Args:
        client_id: Xero client ID
        redirect_uri: Callback URL
        state: Random state for CSRF protection
        code_challenge: PKCE code challenge

    Returns:
        Authorization URL
    """
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{XERO_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_tokens(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
) -> dict:
    """Exchange authorization code for access and refresh tokens.

    Args:
        client_id: Xero client ID
        client_secret: Xero client secret
        code: Authorization code from callback
        redirect_uri: Same redirect URI used for authorization
        code_verifier: PKCE code verifier

    Returns:
        Token response dict with access_token, refresh_token, etc.
    """
    # Create basic auth header
    credentials = f"{client_id}:{client_secret}"
    auth_header = base64.b64encode(credentials.encode()).decode()

    response = httpx.post(
        XERO_TOKEN_URL,
        headers={
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        },
        timeout=30,
    )

    if response.status_code != 200:
        raise Exception(f"Token exchange failed: {response.text}")

    return response.json()


def get_tenant_id(access_token: str) -> tuple:
    """Get the Xero tenant ID from connections endpoint.

    Args:
        access_token: Valid access token

    Returns:
        Tuple of (tenant_id, tenant_name)
    """
    response = httpx.get(
        XERO_CONNECTIONS_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )

    if response.status_code != 200:
        raise Exception(f"Failed to get connections: {response.text}")

    connections = response.json()

    if not connections:
        raise Exception("No Xero organisations connected. Please connect an organisation first.")

    # If multiple orgs, let user choose
    if len(connections) > 1:
        print("\nMultiple Xero organisations found:")
        for i, conn in enumerate(connections, 1):
            print(f"  {i}. {conn['tenantName']} ({conn['tenantType']})")

        while True:
            try:
                choice = int(input("\nSelect organisation number: "))
                if 1 <= choice <= len(connections):
                    selected = connections[choice - 1]
                    break
                print("Invalid selection. Try again.")
            except ValueError:
                print("Please enter a number.")
    else:
        selected = connections[0]

    return selected["tenantId"], selected["tenantName"]


def update_env_file(env_path: Path, updates: dict) -> None:
    """Update .env file with new values.

    Args:
        env_path: Path to .env file
        updates: Dict of key-value pairs to update
    """
    # Create .env if it doesn't exist
    if not env_path.exists():
        # Copy from .env.example if available
        example_path = env_path.parent / ".env.example"
        if example_path.exists():
            env_path.write_text(example_path.read_text())
        else:
            env_path.touch()

    for key, value in updates.items():
        set_key(str(env_path), key, value)


def main():
    """Run the OAuth2 authorization flow."""
    print("=" * 60)
    print("Xero OAuth2 Authorization Helper")
    print("=" * 60)
    print()

    # Load existing .env
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)

    # Get client credentials
    client_id = os.getenv("XERO_CLIENT_ID")
    client_secret = os.getenv("XERO_CLIENT_SECRET")

    if not client_id:
        print("XERO_CLIENT_ID not found in .env file.")
        client_id = input("Enter your Xero Client ID: ").strip()
        if not client_id:
            print("Error: Client ID is required.")
            sys.exit(1)

    if not client_secret:
        print("XERO_CLIENT_SECRET not found in .env file.")
        client_secret = input("Enter your Xero Client Secret: ").strip()
        if not client_secret:
            print("Error: Client Secret is required.")
            sys.exit(1)

    # Generate PKCE values
    code_verifier, code_challenge = generate_pkce()

    # Generate state for CSRF protection
    state = secrets.token_urlsafe(16)

    # Build redirect URI
    redirect_uri = f"http://localhost:{CALLBACK_PORT}{CALLBACK_PATH}"

    # Build authorization URL
    auth_url = build_authorization_url(client_id, redirect_uri, state, code_challenge)

    # Start local server to receive callback
    print(f"\nStarting local server on port {CALLBACK_PORT}...")

    # Use a flag to stop the server
    server_ready = threading.Event()

    def run_server():
        with socketserver.TCPServer(("", CALLBACK_PORT), AuthorizationHandler) as httpd:
            httpd.timeout = 1
            server_ready.set()
            while AuthorizationHandler.authorization_code is None and AuthorizationHandler.error is None:
                httpd.handle_request()

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    server_ready.wait()

    # Open browser
    print("\nOpening browser for Xero authorization...")
    print(f"If browser doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    print("Waiting for authorization...")
    server_thread.join(timeout=300)  # 5 minute timeout

    if AuthorizationHandler.error:
        print(f"\nError: {AuthorizationHandler.error}")
        sys.exit(1)

    if not AuthorizationHandler.authorization_code:
        print("\nError: Authorization timed out.")
        sys.exit(1)

    # Verify state
    if AuthorizationHandler.state_received != state:
        print("\nError: State mismatch - possible CSRF attack.")
        sys.exit(1)

    print("\nAuthorization code received!")
    print("Exchanging code for tokens...")

    # Exchange code for tokens
    try:
        tokens = exchange_code_for_tokens(
            client_id=client_id,
            client_secret=client_secret,
            code=AuthorizationHandler.authorization_code,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
        )
    except Exception as e:
        print(f"\nError exchanging code: {e}")
        sys.exit(1)

    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    print("Tokens received!")
    print("Fetching tenant information...")

    # Get tenant ID
    try:
        tenant_id, tenant_name = get_tenant_id(access_token)
    except Exception as e:
        print(f"\nError getting tenant: {e}")
        sys.exit(1)

    print(f"\nConnected to: {tenant_name}")

    # Update .env file
    print("\nSaving credentials to .env file...")

    updates = {
        "XERO_CLIENT_ID": client_id,
        "XERO_CLIENT_SECRET": client_secret,
        "XERO_TENANT_ID": tenant_id,
        "XERO_ACCESS_TOKEN": access_token,
        "XERO_REFRESH_TOKEN": refresh_token,
    }

    try:
        update_env_file(env_path, updates)
        print("Credentials saved successfully!")
    except Exception as e:
        print(f"\nError saving to .env: {e}")
        print("\nManually add these to your .env file:")
        for key, value in updates.items():
            # Mask tokens for display
            display_value = value[:20] + "..." if len(value) > 20 else value
            print(f"  {key}={display_value}")
        sys.exit(1)

    print()
    print("=" * 60)
    print("SUCCESS! Xero authorization complete.")
    print("=" * 60)
    print()
    print("Your .env file has been updated with:")
    print(f"  - XERO_CLIENT_ID")
    print(f"  - XERO_CLIENT_SECRET")
    print(f"  - XERO_TENANT_ID ({tenant_name})")
    print(f"  - XERO_ACCESS_TOKEN")
    print(f"  - XERO_REFRESH_TOKEN")
    print()
    print("You can now run the sync:")
    print("  python sync.py --dry-run")
    print()


if __name__ == "__main__":
    main()
