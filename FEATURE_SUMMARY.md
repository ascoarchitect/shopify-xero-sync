# Email Marketing Feature - Implementation Summary

## Overview

Added functionality to enable email marketing (subscribe) for all customers in Shopify. This addresses the issue where email marketing consent wasn't transferred during migration from Wix to Shopify.

## Changes Made

### 1. Configuration (`src/config.py`)

Added new configuration option:
- `enable_email_marketing` (bool, default: False) - When enabled, automatically subscribes customers during sync

### 2. Shopify REST Client (`src/shopify_client.py`)

Added method:
- `update_customer_email_marketing(customer_id, accepts_marketing=True)` - Updates a customer's email marketing consent via REST API

### 3. Shopify GraphQL Client (`src/shopify_graphql_client.py`)

Added method:
- `update_customer_email_marketing(customer_id, accepts_marketing=True)` - Updates a customer's email marketing consent via GraphQL mutation

### 4. Sync Engine (`src/sync_engine.py`)

Added methods:
- `_update_customer_email_marketing(customer_id)` - Helper method to update email marketing for a single customer
- `enable_email_marketing_for_all_customers()` - Bulk update all customers to accept email marketing

Modified method:
- `_sync_single_customer()` - Now checks `enable_email_marketing` setting and updates customers during sync if enabled

### 5. Standalone Script (`enable_email_marketing.py`)

New executable script that:
- Fetches all customers from Shopify
- Updates each customer to accept email marketing
- Supports `--dry-run` flag for testing
- Requires confirmation before making changes
- Shows progress and summary
- Handles errors gracefully

### 6. Documentation

Created:
- `EMAIL_MARKETING_GUIDE.md` - Comprehensive guide on using the feature
- Updated `README.md` - Added feature to features list and usage section
- Updated `.env.example` - Added `ENABLE_EMAIL_MARKETING` configuration option

### 7. Testing

Created:
- `test_email_marketing_feature.py` - Smoke test to verify integration

## Usage

### Option 1: One-Time Bulk Update (Recommended for Migration)

```bash
# Dry run first
docker-compose run --rm shopify-xero-sync python enable_email_marketing.py --dry-run

# Actual update
docker-compose run --rm shopify-xero-sync python enable_email_marketing.py
```

### Option 2: Automatic During Sync

Add to `.env`:
```bash
ENABLE_EMAIL_MARKETING=true
```

Then run regular sync:
```bash
docker-compose run --rm shopify-xero-sync
```

## Technical Details

### API Calls

**REST API** (ShopifyClient):
```http
PUT /admin/api/2024-01/customers/{customer_id}.json
Content-Type: application/json

{
  "customer": {
    "id": 123456,
    "email_marketing_consent": {
      "state": "subscribed",
      "opt_in_level": "single_opt_in"
    }
  }
}
```

**Note:** The older `accepts_marketing` field is deprecated. We use the newer `email_marketing_consent` object which provides:
- `state`: "subscribed" or "not_subscribed"
- `opt_in_level`: "single_opt_in", "confirmed_opt_in", or "unknown"
- `consent_updated_at`: Timestamp of last update

**GraphQL API** (ShopifyGraphQLClient):
```graphql
mutation customerUpdate($input: CustomerInput!) {
  customerUpdate(input: $input) {
    customer {
      id
      email
      emailMarketingConsent {
        marketingState
      }
    }
    userErrors {
      field
      message
    }
  }
}

# Variables:
{
  "input": {
    "id": "gid://shopify/Customer/123456",
    "emailMarketingConsent": {
      "marketingState": "SUBSCRIBED",
      "marketingOptInLevel": "SINGLE_OPT_IN"
    }
  }
}
```

**GraphQL values:**
- `marketingState`: "SUBSCRIBED", "NOT_SUBSCRIBED", "UNSUBSCRIBED", "PENDING"
- `marketingOptInLevel`: "SINGLE_OPT_IN", "CONFIRMED_OPT_IN", "UNKNOWN"

### Rate Limiting

- Adds 0.1 second delay between customer updates
- Respects Shopify's rate limits (2 calls/second for REST, cost-based for GraphQL)
- Automatically retries on rate limit errors

### Error Handling

- Non-blocking: If email marketing update fails, sync continues
- Errors are logged but don't stop the sync process
- Failed updates are reported in the summary

## Testing

### Prerequisites

Before testing, ensure your Shopify app has the `write_customers` scope:
1. Check Shopify Partner Dashboard → Your App → Configuration → API access scopes
2. If missing, add `write_customers` and re-authenticate with `python auth_shopify.py`
3. See `SHOPIFY_PERMISSIONS_UPDATE.md` for detailed instructions

### Run Tests

Check customer marketing status:
```bash
python check_customer_marketing.py
```

Test updating a customer:
```bash
python test_update_customer_marketing.py
```

Run the smoke test:
```bash
python3 test_email_marketing_feature.py
```

Or with the virtual environment:
```bash
source venv/bin/activate
python test_email_marketing_feature.py
```

## Compliance Notes

⚠️ **Important**: Before using this feature, ensure you have:
1. Legal basis to send marketing emails
2. Privacy policy covering email marketing
3. Compliance with GDPR, CAN-SPAM, CASL, etc.

See `EMAIL_MARKETING_GUIDE.md` for detailed compliance considerations.

## Files Modified

- `src/config.py` - Added configuration option
- `src/shopify_client.py` - Added REST API method
- `src/shopify_graphql_client.py` - Added GraphQL mutation
- `src/sync_engine.py` - Added bulk update and integration with sync
- `.env.example` - Added configuration documentation
- `README.md` - Updated features and usage sections

## Files Created

- `enable_email_marketing.py` - Standalone script for bulk updates
- `EMAIL_MARKETING_GUIDE.md` - User guide
- `FEATURE_SUMMARY.md` - This file
- `test_email_marketing_feature.py` - Integration test

## Backward Compatibility

✅ Fully backward compatible:
- Feature is disabled by default (`enable_email_marketing=false`)
- Existing syncs work exactly as before
- No database schema changes required
- No breaking changes to existing APIs

## Performance Impact

When `enable_email_marketing=true`:
- Adds one API call per customer during sync
- Minimal impact: ~0.1 seconds per customer
- For 500 customers: ~50 seconds additional time

When disabled (default):
- Zero performance impact
- No additional API calls

## Future Enhancements

Potential improvements:
1. Track email marketing status in database to avoid redundant updates
2. Add option to unsubscribe customers
3. Batch updates using GraphQL bulk operations
4. Add email marketing status to customer sync checksum
5. Support for SMS marketing consent
