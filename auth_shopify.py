#!/usr/bin/env python3
"""Shopify OAuth2 Authentication Helper.

This script helps you authenticate with Shopify using the modern OAuth2 flow
required for apps created in the Shopify Dev Dashboard (post-2026).

Usage:
    python auth_shopify.py

The script will:
    1. Guide you through creating an app in the Dev Dashboard
    2. Start a local OAuth callback server
    3. Open your browser for authorization
    4. Exchange the authorization code for an access token
    5. Save the token to your .env file

Requirements:
    pip install httpx python-dotenv aiohttp
"""

import asyncio
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv, set_key
except ImportError:
    print("Error: python-dotenv not installed. Run: pip install python-dotenv")
    sys.exit(1)

try:
    import httpx
except ImportError:
    print("Error: httpx not installed. Run: pip install httpx")
    sys.exit(1)

try:
    import aiohttp
except ImportError:
    print("Error: aiohttp not installed. Run: pip install aiohttp")
    sys.exit(1)

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.shopify_oauth import get_access_token_interactive


def print_instructions():
    """Print step-by-step instructions for setting up Shopify OAuth."""
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║              SHOPIFY OAUTH2 SETUP INSTRUCTIONS                        ║
║                    (Dev Dashboard Method)                             ║
╚══════════════════════════════════════════════════════════════════════╝

This is the NEW method required for apps created after January 2026.

Follow these steps:

┌─────────────────────────────────────────────────────────────────────┐
│ STEP 1: Create App in Dev Dashboard                                 │
├─────────────────────────────────────────────────────────────────────┤
│  1. Go to: https://partners.shopify.com/                           │
│  2. Log in with your Shopify Partner account                        │
│     (Create one if you don't have it - it's free)                   │
│  3. Click "Apps" in the left sidebar                                │
│  4. Click "Create app"                                              │
│  5. Choose "Create app manually"                                    │
│  6. App name: "Xero Sync" (or any name)                            │
│  7. Click "Create"                                                  │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ STEP 2: Configure App                                               │
├─────────────────────────────────────────────────────────────────────┤
│  1. In your app, go to "Configuration" tab                          │
│  2. Under "App URL", enter: http://localhost:8080                   │
│  3. Under "Allowed redirection URL(s)", add:                        │
│     http://localhost:8080/callback                                  │
│  4. Scroll down to "Access scopes"                                  │
│  5. Select these scopes:                                            │
│     ✓ read_customers                                                │
│     ✓ read_products                                                 │
│     ✓ read_orders                                                   │
│  6. Click "Save"                                                    │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ STEP 3: Get Client Credentials                                      │
├─────────────────────────────────────────────────────────────────────┤
│  1. Go to "Overview" tab                                            │
│  2. Find "Client credentials" section                               │
│  3. Copy the "Client ID"                                            │
│  4. Click "Show" next to "Client secret" and copy it                │
│                                                                     │
│  ⚠️  Keep these secret! Don't commit them to git.                   │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ STEP 4: Install App to Your Store                                   │
├─────────────────────────────────────────────────────────────────────┤
│  1. In Dev Dashboard, go to "Overview" tab                          │
│  2. Under "Test your app", click "Select store"                     │
│  3. Choose your development store or enter your store URL           │
│  4. This generates an install link - DON'T click it yet!            │
│     (This script will handle the OAuth flow)                        │
└─────────────────────────────────────────────────────────────────────┘

""")


def validate_shop_url(url: str) -> str:
    """Validate and normalize the Shopify store URL."""
    url = url.strip().rstrip("/")
    
    if not url.startswith("http"):
        url = f"https://{url}"
    
    url = url.replace("http://", "https://")
    
    if ".myshopify.com" not in url:
        # Assume it's just the store name
        store_name = url.replace("https://", "").split(".")[0]
        url = f"https://{store_name}.myshopify.com"
    
    return url


async def test_access_token(shop_url: str, access_token: str) -> dict:
    """Test the access token by fetching shop info."""
    api_url = f"{shop_url}/admin/api/2024-01/shop.json"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            api_url,
            headers={
                "X-Shopify-Access-Token": access_token,
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        
        if response.status_code == 401:
            raise Exception("Invalid access token")
        
        if response.status_code != 200:
            raise Exception(f"API error: {response.status_code} - {response.text}")
        
        return response.json().get("shop", {})


def update_env_file(env_path: Path, updates: dict) -> None:
    """Update .env file with new values."""
    if not env_path.exists():
        example_path = env_path.parent / ".env.example"
        if example_path.exists():
            env_path.write_text(example_path.read_text())
        else:
            env_path.touch()
    
    for key, value in updates.items():
        set_key(str(env_path), key, value)


async def main_async():
    """Run the async OAuth flow."""
    print("=" * 70)
    print("Shopify OAuth2 Authentication Helper")
    print("=" * 70)
    
    # Load existing .env
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)
    
    # Check for existing credentials
    existing_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
    existing_shop = os.getenv("SHOPIFY_SHOP_URL")
    
    if existing_token and existing_shop:
        print(f"\nExisting access token found for: {existing_shop}")
        response = input("Do you want to re-authenticate? (y/N): ").strip().lower()
        if response != "y":
            print("\nTesting existing token...")
            try:
                shop_info = await test_access_token(existing_shop, existing_token)
                print(f"\n✓ Token is valid for: {shop_info.get('name', 'Unknown')}")
                return
            except Exception as e:
                print(f"\n✗ Existing token invalid: {e}")
                print("Let's get a new one.\n")
    
    # Show instructions
    print_instructions()
    
    input("Press Enter when you're ready to continue...")
    print()
    
    # Get credentials
    print("Enter your app credentials from the Dev Dashboard:")
    print()
    
    client_id = input("Client ID: ").strip()
    if not client_id:
        print("Error: Client ID is required")
        sys.exit(1)
    
    client_secret = input("Client Secret: ").strip()
    if not client_secret:
        print("Error: Client Secret is required")
        sys.exit(1)
    
    shop_url = input("Store URL (e.g., my-store.myshopify.com): ").strip()
    if not shop_url:
        print("Error: Store URL is required")
        sys.exit(1)
    
    shop_url = validate_shop_url(shop_url)
    print(f"  → Using: {shop_url}")
    
    # Run OAuth flow
    print("\n" + "=" * 70)
    print("Starting OAuth Flow")
    print("=" * 70)
    print()
    print("This will:")
    print("  1. Start a local server on http://localhost:8080")
    print("  2. Open your browser for authorization")
    print("  3. Wait for you to approve the app")
    print("  4. Exchange the code for an access token")
    print()
    
    input("Press Enter to start...")
    print()
    
    try:
        access_token = await get_access_token_interactive(
            client_id=client_id,
            client_secret=client_secret,
            shop_url=shop_url,
        )
        
        print("\n✓ Successfully obtained access token!")
        
    except Exception as e:
        print(f"\n✗ OAuth flow failed: {e}")
        sys.exit(1)
    
    # Test the token
    print("\nTesting access token...")
    try:
        shop_info = await test_access_token(shop_url, access_token)
        print(f"\n✓ Token is valid!")
        print(f"  Shop: {shop_info.get('name', 'Unknown')}")
        print(f"  Domain: {shop_info.get('domain', 'Unknown')}")
        print(f"  Email: {shop_info.get('email', 'Unknown')}")
        print(f"  Plan: {shop_info.get('plan_name', 'Unknown')}")
    except Exception as e:
        print(f"\n✗ Token test failed: {e}")
        sys.exit(1)
    
    # Save to .env
    print("\n" + "=" * 70)
    print("Saving credentials...")
    print("=" * 70)
    
    updates = {
        "SHOPIFY_SHOP_URL": shop_url,
        "SHOPIFY_CLIENT_ID": client_id,
        "SHOPIFY_CLIENT_SECRET": client_secret,
        "SHOPIFY_ACCESS_TOKEN": access_token,
    }
    
    try:
        update_env_file(env_path, updates)
        print("\n✓ Credentials saved to .env file!")
    except Exception as e:
        print(f"\n✗ Error saving to .env: {e}")
        print("\nManually add these to your .env file:")
        for key, value in updates.items():
            if "SECRET" in key or "TOKEN" in key:
                print(f"  {key}={value[:20]}...")
            else:
                print(f"  {key}={value}")
        sys.exit(1)
    
    print()
    print("=" * 70)
    print("SUCCESS! Shopify OAuth configured.")
    print("=" * 70)
    print()
    print("Next steps:")
    print("  1. Run: python auth_xero.py   (if not done yet)")
    print("  2. Run: python sync.py --dry-run")
    print()


def main():
    """Main entry point."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        sys.exit(1)


if __name__ == "__main__":
    main()
