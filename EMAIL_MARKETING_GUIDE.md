# Email Marketing Setup Guide

This guide explains how to enable email marketing for all your Shopify customers, which is particularly useful if you migrated from another platform (like Wix) where email marketing consent wasn't properly transferred.

## Overview

The sync system now includes functionality to set all customers in Shopify to accept email marketing (subscribe). This can be done in two ways:

1. **One-time bulk update** - Run a dedicated script to update all customers at once
2. **Automatic during sync** - Enable a setting to automatically subscribe customers during regular syncs

## Prerequisites

⚠️ **Important**: This feature requires the `write_customers` Shopify API scope.

If you get an error like:
```
API error 403: This action requires merchant approval for write_customers scope
```

You need to update your Shopify app permissions. See **[SHOPIFY_PERMISSIONS_UPDATE.md](SHOPIFY_PERMISSIONS_UPDATE.md)** for detailed instructions.

**Quick fix:**
1. Go to Shopify Partner Dashboard → Your App → Configuration
2. Add `write_customers` to API access scopes
3. Run `python auth_shopify.py` to re-authenticate
4. Try again

## Method 1: One-Time Bulk Update (Recommended)

This is the recommended approach for initial migration. It updates all existing customers in one go.

### Step 1: Dry Run First

Always run a dry run first to see what would be updated:

```bash
# Using Docker
docker-compose run --rm shopify-xero-sync python enable_email_marketing.py --dry-run

# Or locally (if you have Python environment set up)
python enable_email_marketing.py --dry-run
```

This will show you:
- How many customers will be updated
- Which customers will be affected
- Any potential errors

### Step 2: Run the Actual Update

Once you're satisfied with the dry run results:

```bash
# Using Docker
docker-compose run --rm shopify-xero-sync python enable_email_marketing.py

# Or locally
python enable_email_marketing.py
```

The script will:
1. Ask for confirmation before proceeding
2. Fetch all customers from Shopify
3. Update each customer to accept email marketing
4. Show progress and any errors
5. Display a summary at the end

### What It Does

The script updates each customer's email marketing consent to:
- **Marketing State**: SUBSCRIBED
- **Opt-in Level**: SINGLE_OPT_IN

This means customers will be subscribed to your email marketing campaigns in Shopify.

## Method 2: Automatic During Sync

If you want to automatically subscribe new customers during regular syncs, you can enable this in your configuration.

### Step 1: Update .env File

Add or update this line in your `.env` file:

```bash
ENABLE_EMAIL_MARKETING=true
```

### Step 2: Run Regular Sync

Now when you run the regular sync, it will automatically update email marketing consent for all customers it processes:

```bash
docker-compose run --rm shopify-xero-sync
```

### When to Use This Method

This method is useful if:
- You want ongoing automatic subscription for all customers
- You're continuously importing customers from another system
- You want to ensure all customers are always subscribed

**Note**: This adds a small overhead to each sync as it makes an additional API call per customer.

## Important Considerations

### Legal Compliance

⚠️ **Important**: Before enabling email marketing for customers, ensure you have:

1. **Legal basis** to send marketing emails (e.g., legitimate interest, consent from previous platform)
2. **Privacy policy** that covers email marketing
3. **Unsubscribe mechanism** in your emails (Shopify provides this automatically)
4. **Compliance** with regulations like GDPR, CAN-SPAM, CASL, etc.

### Rate Limiting

The script respects Shopify's rate limits:
- Adds a small delay between updates (0.1 seconds)
- Handles rate limit errors automatically
- For large customer bases (1000+), the script may take several minutes

### Error Handling

If errors occur:
- The script continues processing other customers
- Errors are logged and displayed in the summary
- You can re-run the script to retry failed updates

## Verification

After running the script, you can verify the changes in Shopify:

1. Go to your Shopify admin
2. Navigate to Customers
3. Click on any customer
4. Check the "Email marketing" section - it should show "Subscribed"

## Troubleshooting

### "API error 403: This action requires merchant approval for write_customers scope"

Your Shopify app doesn't have write permissions. See **[SHOPIFY_PERMISSIONS_UPDATE.md](SHOPIFY_PERMISSIONS_UPDATE.md)** for instructions on:
1. Adding `write_customers` scope to your app
2. Re-authenticating to get updated permissions

### "Failed to connect to Shopify API"

Make sure you've authenticated with Shopify:
```bash
python auth_shopify.py
```

### "Rate limit exceeded"

The script handles this automatically, but if you see persistent rate limit errors:
- Wait a few minutes and try again
- The script will automatically retry with delays

### "Customer update errors"

Some customers may fail to update due to:
- Invalid email addresses
- Archived customers
- API permissions issues

Check the error messages in the output for specific details.

## Example Output

```
============================================================
SHOPIFY EMAIL MARKETING ENABLER
============================================================
Using Shopify GraphQL API
Verifying Shopify connection...
Shopify GraphQL API connection successful: Your Store Name
==================================================
ENABLING EMAIL MARKETING FOR ALL CUSTOMERS
==================================================
Fetching all customers from Shopify...
Fetched 250 customers from Shopify
Total customers fetched: 523
Found 523 customers to update
Enabled email marketing for customer 123456 (customer@example.com)
Enabled email marketing for customer 123457 (another@example.com)
...
==================================================
Email marketing update complete: 523 updated, 0 errors
==================================================

============================================================
SUMMARY
============================================================
Customers updated: 523
Errors: 0
============================================================
```

## Disabling the Feature

To disable automatic email marketing updates during sync:

1. Edit your `.env` file
2. Set `ENABLE_EMAIL_MARKETING=false` (or remove the line)
3. Run sync as normal

The one-time bulk update script can be run anytime regardless of this setting.

## Support

If you encounter issues:
1. Check the logs in `logs/sync.log`
2. Run with `LOG_LEVEL=DEBUG` in `.env` for more details
3. Verify your Shopify API permissions include customer write access
