# OAuth Setup Quickstart

## TL;DR

Shopify changed their authentication in 2026. You now need to use OAuth instead of simple access tokens.

## What You Need

From the [Shopify Dev Dashboard](https://partners.shopify.com/):
- Client ID
- Client Secret

## Setup Steps

### 1. Create Shopify App (5 minutes)

1. Go to https://partners.shopify.com/
2. Create a free Partner account if needed
3. Apps → Create app → Create app manually
4. Name it "Xero Sync"
5. Configuration tab:
   - App URL: `http://localhost:8080`
   - Redirect URL: `http://localhost:8080/callback`
   - Scopes: `read_customers`, `read_products`, `read_orders`
   - Save
6. Overview tab → Copy Client ID and Client Secret

### 2. Run OAuth Flow (2 minutes)

```bash
# Install dependencies
pip install -r requirements.txt

# Run OAuth helper
python auth_shopify.py
```

This will:
- Ask for your Client ID, Client Secret, and store URL
- Start a local server
- Open your browser
- Ask you to approve the app
- Save the access token to `.env`

### 3. Done!

Your `.env` file now has:
```bash
SHOPIFY_SHOP_URL=https://your-store.myshopify.com
SHOPIFY_CLIENT_ID=abc123...
SHOPIFY_CLIENT_SECRET=def456...
SHOPIFY_ACCESS_TOKEN=shpat_789...
```

The access token doesn't expire, so you only need to do this once.

## Troubleshooting

**"I only see Client ID and Secret, no access token"**
- That's correct! You get the access token by running `python auth_shopify.py`

**"Browser doesn't open"**
- Copy the URL from the terminal and paste it into your browser

**"Invalid redirect URI"**
- Make sure you added `http://localhost:8080/callback` in the Dev Dashboard

**"I have a legacy shpat_ token from Shopify Admin"**
- It still works for now, but migrate to OAuth to be future-proof
- See [SHOPIFY_OAUTH_MIGRATION.md](SHOPIFY_OAUTH_MIGRATION.md)

## What Changed?

| Old (Legacy) | New (OAuth) |
|--------------|-------------|
| Create app in Shopify Admin | Create app in Dev Dashboard |
| Copy/paste `shpat_` token | Run OAuth flow to get token |
| Simple but deprecated | More steps but future-proof |

## Need Help?

See the full migration guide: [SHOPIFY_OAUTH_MIGRATION.md](SHOPIFY_OAUTH_MIGRATION.md)
