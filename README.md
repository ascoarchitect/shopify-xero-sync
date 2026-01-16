# Shopify-Xero Sync System

A local Docker-based synchronization system that syncs customers, products, and orders from Shopify to Xero accounting software. Built for small businesses with <500 products and <50 orders/day.

## Features

- **Customer Sync**: Syncs Shopify customers to Xero contacts
- **Change Detection**: Uses checksums to detect actual changes before syncing
- **Duplicate Prevention**: Checks by email before creating new contacts
- **Rate Limiting**: Respects both Shopify (2/sec) and Xero (60/min) rate limits
- **Retry Logic**: Failed syncs are recorded and can be retried
- **Dry Run Mode**: Test what would happen without making changes
- **Idempotent**: Safe to run multiple times

## Prerequisites

- Docker and Docker Compose
- Shopify Partner account (free at [partners.shopify.com](https://partners.shopify.com/))
- Shopify app created in Dev Dashboard with OAuth credentials
- Xero OAuth2 app credentials

## Quick Start

1. **Clone and configure**:
   ```bash
   cd shopify-xero-sync
   cp .env.example .env
   # Edit .env with your credentials (see Setup section below)
   ```

2. **Authenticate with Shopify**:
   ```bash
   python auth_shopify.py
   # Follow the prompts to complete OAuth flow
   ```

3. **Authenticate with Xero**:
   ```bash
   python auth_xero.py
   # Follow the prompts to complete OAuth flow
   ```

4. **Build the container**:
   ```bash
   docker-compose build
   ```

5. **Run a dry-run first**:
   ```bash
   docker-compose run --rm shopify-xero-sync python sync.py --dry-run
   ```

6. **Run actual sync**:
   ```bash
   docker-compose run --rm shopify-xero-sync
   ```

## Configuration

### Shopify Setup (OAuth Method)

1. **Create a Shopify Partner account** at [partners.shopify.com](https://partners.shopify.com/) (free)

2. **Create an app**:
   - Go to Apps → Create app → Create app manually
   - Name: "Xero Sync" (or your choice)

3. **Configure the app**:
   - Configuration tab:
     - App URL: `http://localhost:8080`
     - Allowed redirection URL(s): `http://localhost:8080/callback`
   - Access scopes: `read_customers`, `read_products`, `read_orders`
   - Save

4. **Get credentials**:
   - Overview tab → Copy Client ID and Client Secret

5. **Run OAuth flow**:
   ```bash
   python auth_shopify.py
   ```
   This will open your browser, authorize the app, and save the access token to `.env`

### Xero Setup

1. Create app at [Xero Developer Portal](https://developer.xero.com/)
2. Set redirect URI to `http://localhost:8080/callback`
3. Get Client ID and Client Secret
4. Run `python auth_xero.py` to complete OAuth flow
5. Tokens are automatically refreshed by the SDK

### Environment Variables

Copy `.env.example` to `.env` and fill in:

```bash
# Shopify (from Dev Dashboard)
SHOPIFY_SHOP_URL=https://your-store.myshopify.com
SHOPIFY_CLIENT_ID=your_client_id
SHOPIFY_CLIENT_SECRET=your_client_secret
SHOPIFY_ACCESS_TOKEN=  # Obtained via auth_shopify.py

# Xero (from developer.xero.com)
XERO_CLIENT_ID=your_client_id
XERO_CLIENT_SECRET=your_client_secret
XERO_TENANT_ID=your_tenant_id
XERO_REFRESH_TOKEN=  # Obtained via auth_xero.py

# Optional
LOG_LEVEL=INFO
DRY_RUN=false
```

## Usage

### Run Full Sync
```bash
docker-compose run --rm shopify-xero-sync
```

### Dry Run (no changes made)
```bash
docker-compose run --rm shopify-xero-sync python sync.py --dry-run
```

### Retry Failed Syncs
```bash
docker-compose run --rm shopify-xero-sync python sync.py --retry
```

### View Statistics
```bash
docker-compose run --rm shopify-xero-sync python sync.py --stats
```

### Run Tests
```bash
docker-compose run --rm shopify-xero-sync pytest -v
```

## Project Structure

```
shopify-xero-sync/
├── src/
│   ├── config.py           # Configuration management
│   ├── constants.py        # GL code mappings and business rules
│   ├── database.py         # SQLite operations
│   ├── models.py           # Pydantic data models
│   ├── checksums.py        # Change detection
│   ├── shopify_client.py   # Shopify API client
│   ├── shopify_oauth.py    # Shopify OAuth2 flow handler
│   ├── xero_client.py      # Xero API client
│   └── sync_engine.py      # Core sync logic
├── tests/                  # Test suite
├── data/                   # SQLite database (gitignored)
├── logs/                   # Application logs (gitignored)
├── sync.py                 # Main entry point
├── auth_shopify.py         # Shopify OAuth helper
├── auth_xero.py            # Xero OAuth helper
├── Dockerfile              # Container definition
├── docker-compose.yml      # Container orchestration
├── requirements.txt        # Python dependencies
└── .env.example            # Example configuration
```

## How It Works

1. **Fetch from Shopify**: Retrieves customers (and later products/orders)
2. **Calculate Checksum**: Creates hash of key fields for change detection
3. **Check SQLite**: Looks for existing mapping to Xero entity
4. **Compare**: Determines if entity is new, changed, or unchanged
5. **Sync to Xero**: Creates or updates entity in Xero
6. **Record Mapping**: Saves mapping for future sync runs

## Database

The SQLite database is a disposable cache that can be rebuilt from the APIs. It contains:

- **sync_mappings**: Links Shopify IDs to Xero IDs
- **sync_history**: Records of each sync run
- **sync_errors**: Failed operations for retry

To rebuild:
```bash
rm data/sync.db
docker-compose run --rm shopify-xero-sync
```

## Xero OAuth2 Setup

1. Create app at [Xero Developer Portal](https://developer.xero.com/) or within your organisation
2. Set redirect URI to `http://localhost:8080/callback`
3. Get Client ID and Client Secret from app overview
4. Run `python auth_xero.py` to complete OAuth flow
5. Tokens are automatically refreshed (30-minute expiry, auto-renewed)

## Shopify OAuth2 Setup

1. Create Partner account at [Shopify Partners](https://partners.shopify.com/) or within your tenant [Shopify Dev](https://dev.shopify.com/)
2. Create app in Dev Dashboard
3. Configure redirect URI: `http://localhost:8080/callback`
4. Get Client ID and Client Secret from app overview
5. Run `python auth_shopify.py` to complete OAuth flow
6. Access token doesn't expire (offline token)

## Troubleshooting

### "Authentication failed"
- Check your API credentials in `.env`
- For Shopify: Run `python auth_shopify.py` to re-authenticate
- For Xero: Run `python auth_xero.py` to re-authenticate
- Tokens are automatically refreshed by the SDK

### "Rate limit exceeded"
- The system handles this automatically with retries
- For persistent issues, increase `RETRY_DELAY` in `.env`

### "Duplicate records created"
- Check database for missing mappings
- Ensure Shopify entities have unique emails/SKUs

### "Browser doesn't open during OAuth"
- Copy the authorization URL from the terminal
- Paste it into your browser manually

### "Invalid redirect URI"
- Ensure you added `http://localhost:8080/callback` to both Shopify and Xero app configurations

## Development

### Run locally (without Docker)
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python sync.py --dry-run
```

### Run tests
```bash
pytest -v --cov=src --cov-report=html
```

## License

Apache 2.0 License - see LICENSE file for details.
