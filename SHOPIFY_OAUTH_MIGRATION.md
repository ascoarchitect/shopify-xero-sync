# Shopify OAuth Migration Guide

## What Changed?

Starting January 1, 2026, Shopify deprecated the legacy "custom apps" created directly in the Shopify Admin. The new approach requires:

- **Old Way (Legacy)**: Create custom app in Shopify Admin → Get `shpat_` access token → Use directly
- **New Way (OAuth)**: Create app in Dev Dashboard → Get Client ID/Secret → Run OAuth flow → Get access token

## Why This Change?

The OAuth approach is more secure and scalable:
- Tokens can be revoked without recreating the app
- Better audit trail of app installations
- Supports multi-store installations
- Aligns with industry standards

## Migration Steps

### 1. Create App in Dev Dashboard

1. Go to [Shopify Partners](https://partners.shopify.com/)
2. Create a Partner account (free) if you don't have one
3. Click "Apps" → "Create app" → "Create app manually"
4. Name it (e.g., "Xero Sync")

### 2. Configure App

1. Go to "Configuration" tab
2. Set **App URL**: `http://localhost:8080`
3. Set **Allowed redirection URL(s)**: `http://localhost:8080/callback`
4. Under "Access scopes", select:
   - `read_customers`
   - `read_products`
   - `read_orders`
5. Click "Save"

### 3. Get Credentials

1. Go to "Overview" tab
2. Copy the **Client ID**
3. Click "Show" and copy the **Client Secret**

### 4. Run OAuth Flow

```bash
python auth_shopify.py
```

This will:
- Start a local OAuth callback server
- Open your browser for authorization
- Exchange the authorization code for an access token
- Save everything to your `.env` file

### 5. Update Your .env File

Your `.env` should now have:

```bash
SHOPIFY_SHOP_URL=https://your-store.myshopify.com
SHOPIFY_CLIENT_ID=your_client_id
SHOPIFY_CLIENT_SECRET=your_client_secret
SHOPIFY_ACCESS_TOKEN=shpat_xxxxx  # Obtained via OAuth
```

## What About Legacy Custom Apps?

If you already have a legacy custom app with a `shpat_` token:

- **It still works** (for now)
- Shopify hasn't announced when they'll stop working
- But you should migrate to be future-proof

## Token Differences

| Token Type | Prefix | How to Get | Expires? |
|------------|--------|------------|----------|
| Legacy Custom App | `shpat_` | Shopify Admin | No |
| OAuth Offline | `shpat_` | OAuth flow | No |
| OAuth Online | `shpua_` | OAuth flow | Yes (24h) |

This integration uses **OAuth Offline** tokens, which don't expire (just like legacy tokens).

## Troubleshooting

### "Client credentials cannot be performed on this shop"

The client credentials grant only works when the app and store are owned by the same organization. For merchant stores, you must use the authorization code grant (which this script does).

### "Missing access token"

Make sure you've run `python auth_shopify.py` to complete the OAuth flow.

### "Invalid redirect URI"

Make sure you added `http://localhost:8080/callback` to the "Allowed redirection URL(s)" in your app configuration.

### Browser doesn't open

The script will print the authorization URL. Copy and paste it into your browser manually.

## Code Changes Summary

### Updated Files

1. **src/config.py**: Changed from `shopify_api_key`/`shopify_api_secret` to `shopify_client_id`/`shopify_client_secret`
2. **src/shopify_client.py**: Added support for setting access token dynamically
3. **src/shopify_oauth.py**: New module for OAuth flow
4. **auth_shopify.py**: Complete rewrite to handle OAuth
5. **requirements.txt**: Added `aiohttp` for OAuth callback server
6. **.env.example**: Updated to reflect new credential names

### Backward Compatibility

The code still works with existing `SHOPIFY_ACCESS_TOKEN` values. If you have a legacy token, you can keep using it by:

1. Setting dummy values for `SHOPIFY_CLIENT_ID` and `SHOPIFY_CLIENT_SECRET`
2. Keeping your existing `SHOPIFY_ACCESS_TOKEN`

But we recommend migrating to OAuth for future-proofing.

## References

- [Shopify OAuth Documentation](https://shopify.dev/docs/apps/build/authentication-authorization)
- [Dev Dashboard](https://partners.shopify.com/)
- [Authorization Code Grant](https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens/authorization-code-grant)
