# Quick Start: Enable Email Marketing for All Customers

## TL;DR

If you migrated from Wix and your customers aren't subscribed to email marketing in Shopify:

### Step 1: Add Write Permission (One-time setup)
```bash
# 1. Go to Shopify Partner Dashboard → Your App → Configuration
# 2. Add 'write_customers' to API access scopes
# 3. Re-authenticate:
python auth_shopify.py
```

### Step 2: Run the Script
```bash
# Test first (dry run)
docker-compose run --rm shopify-xero-sync python enable_email_marketing.py --dry-run

# Then do it for real
docker-compose run --rm shopify-xero-sync python enable_email_marketing.py
```

## What This Does

Sets all your Shopify customers to "Accept Email Marketing" (subscribed) by updating the `email_marketing_consent.state` field to `"subscribed"`.

## Before You Run

⚠️ **Legal**: Make sure you have permission to send marketing emails to these customers!

⚠️ **Permissions**: Your Shopify app needs `write_customers` scope. If you get a 403 error, see [SHOPIFY_PERMISSIONS_UPDATE.md](SHOPIFY_PERMISSIONS_UPDATE.md).

## Options

### One-Time Update (Best for Migration)

```bash
python enable_email_marketing.py
```

- Updates all existing customers once
- Shows progress and summary
- Asks for confirmation

### Automatic During Sync

Add to `.env`:
```bash
ENABLE_EMAIL_MARKETING=true
```

Then run normal sync:
```bash
docker-compose run --rm shopify-xero-sync
```

- Updates customers automatically during each sync
- Good for ongoing imports

## Verification

After running, check in Shopify Admin:
1. Go to Customers
2. Click any customer
3. Look for "Email marketing: Subscribed"

## Need Help?

See `EMAIL_MARKETING_GUIDE.md` for detailed instructions and troubleshooting.
