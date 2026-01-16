# Shopify-Xero Sync System

## Project Overview

This is a local Docker-based synchronization system that syncs customers, products, and orders from Shopify to Xero accounting software. Built for small businesses with <50 products and <10 orders/day.

**Key Philosophy**: Simple, reliable, cost-free sync that prevents duplicates and can recover from failures.

## Business Context

- **Owner**: Adam (Director of Cloud & Transformation at TCS)
- **Use Case**: Wax Pop (Independent Business) creating wax melts and handmade gifts
- **Volume**: <50 products, <10 orders/day
- **Constraints**: No infrastructure costs, must run locally, must be reliable
- **Critical Requirement**: Never create duplicate records in Xero (accounting integrity)

## Architecture Overview

### Core Principles

1. **Change Detection First**: Use checksums to detect actual changes before syncing
2. **Idempotent Operations**: Safe to run multiple times without side effects
3. **Disposable State**: SQLite is just a cache - can be rebuilt from APIs
4. **Fail Gracefully**: Single entity failures don't stop the entire sync
5. **Explicit over Implicit**: Prefer clear, verbose code over clever shortcuts

### Data Flow
```
Shopify API → Checksum Check → SQLite Mapping Check → Xero Comparison → Update Decision
                    ↓                    ↓                     ↓
              Changed?           Exists in Xero?        Push Update?
                    ↓                    ↓                     ↓
              Yes → Continue      Yes → Compare      Yes → Update Xero
              No → Skip          No → Create        No → Skip
```

### Technology Stack

- **Language**: Python 3.11+
- **HTTP Client**: httpx (async support)
- **Data Validation**: Pydantic v2
- **Database**: SQLite3
- **Testing**: pytest with pytest-asyncio, pytest-httpx
- **Container**: Docker (Alpine or slim base)
- **APIs**: Shopify REST API, Xero API (both OAuth2)

## Project Structure
```
shopify-xero-sync/
├── src/                          # Application code
│   ├── __init__.py
│   ├── shopify_client.py         # Shopify API wrapper
│   ├── xero_client.py            # Xero API wrapper  
│   ├── sync_engine.py            # Core sync orchestration
│   ├── models.py                 # Pydantic data models
│   ├── database.py               # SQLite operations
│   ├── checksums.py              # Change detection logic
│   └── config.py                 # Configuration management
├── tests/                        # Test suite
│   ├── unit/                     # Unit tests (isolated)
│   ├── integration/              # Integration tests (with mocks)
│   ├── fixtures/                 # Test data and mocks
│   └── conftest.py               # Pytest configuration
├── .subagents/                   # Claude Code sub-agents
│   ├── integration-architect.md
│   ├── test-engineer.md
│   ├── security-auditor.md
│   ├── docker-devops-engineer.md
│   └── qa-integration-tester.md
├── data/                         # SQLite database (gitignored)
├── logs/                         # Application logs (gitignored)
├── Dockerfile                    # Container definition
├── docker-compose.yml            # Container orchestration
├── requirements.txt              # Python dependencies (pinned)
├── .env.example                  # Example environment variables
├── .gitignore                    # Git exclusions
├── README.md                     # User documentation
├── CLAUDE.md                     # This file
└── sync.py                       # Main entry point
```

## Database Schema

### sync_mappings Table
Maps Shopify entities to their Xero counterparts.
```sql
CREATE TABLE sync_mappings (
    shopify_id TEXT PRIMARY KEY,      -- Shopify entity ID (e.g., "123456789")
    xero_id TEXT NOT NULL,            -- Xero entity ID (e.g., UUID)
    entity_type TEXT NOT NULL,        -- "customer", "product", "order"
    last_synced_at TIMESTAMP,         -- When this mapping was last used
    shopify_updated_at TIMESTAMP,     -- Shopify's last updated timestamp
    checksum TEXT                     -- SHA256 of key fields for change detection
);
```

### sync_history Table
Tracks each sync run for auditing and debugging.
```sql
CREATE TABLE sync_history (
    run_id TEXT PRIMARY KEY,          -- UUID for this sync run
    started_at TIMESTAMP,             -- When sync started
    completed_at TIMESTAMP,           -- When sync completed (NULL if running)
    status TEXT,                      -- "running", "success", "failed"
    entities_processed INTEGER,       -- Count of entities processed
    errors TEXT                       -- JSON array of error messages
);
```

### sync_errors Table
Stores failed operations for manual review and retry.
```sql
CREATE TABLE sync_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT,                 -- "customer", "product", "order"
    shopify_id TEXT,                  -- Shopify ID that failed
    error_message TEXT,               -- Full error message
    occurred_at TIMESTAMP,            -- When error occurred
    retry_count INTEGER DEFAULT 0     -- Number of retry attempts
);
```

## Key Design Decisions

### 1. Why SQLite?
- **Disposable**: Can be deleted and rebuilt from APIs
- **No infrastructure**: Single file, no server needed
- **Good enough**: Handles our volume easily (<1000 entities)
- **Portable**: Easy to backup, move, inspect

### 2. Why Checksums?
- **Efficiency**: Detect changes without fetching full Xero entity
- **Fast comparison**: SHA256 is fast and collision-resistant
- **Bandwidth savings**: Skip API calls for unchanged entities

### 3. Why Async/Await?
- **Concurrent API calls**: Fetch from Shopify and Xero simultaneously
- **Better performance**: Don't block on I/O
- **Rate limit friendly**: Easy to implement delays

### 4. Why Docker?
- **Reproducible**: Same environment everywhere
- **No local dependencies**: Everything in container
- **Easy scheduling**: Can run via cron without conflicts
- **Isolation**: Doesn't pollute local Python environment

### 5. Why Local (not AWS Lambda)?
- **Start simple**: Validate logic before adding infrastructure
- **Lower volume**: <10 orders/day doesn't need serverless scale
- **Zero cost**: No AWS bills for development/testing
- **Easy debugging**: Can inspect logs and database locally
- **Future migration**: Can lift to Lambda later if needed

## Coding Conventions

### Python Style
- **PEP 8**: Follow standard Python style guide
- **Type hints**: Use everywhere (helps catch bugs early)
- **Docstrings**: All public functions get docstrings
- **Async first**: Use async/await for all I/O operations

### Error Handling
```python
# Distinguish between retryable and permanent errors
try:
    result = await api_call()
except RateLimitError:
    # Retryable - wait and retry
    await asyncio.sleep(retry_delay)
except ValidationError:
    # Permanent - log and skip
    logger.error(f"Invalid data: {entity_id}")
    store_error(entity_id, error)
```

### Logging
```python
# Use structured logging with context
logger.info(
    "Syncing customer",
    extra={
        "shopify_id": customer.id,
        "email": customer.email,
        "action": "create"
    }
)

# NEVER log sensitive data
logger.info(f"Token: {access_token}")  # ❌ NO!
logger.info("Authentication successful")  # ✅ YES
```

### Testing
```python
# All async tests need decorator
@pytest.mark.asyncio
async def test_sync_customer(httpx_mock):
    """Test customer sync with mocked API"""
    # Arrange: Set up mocks
    httpx_mock.add_response(...)
    
    # Act: Call function
    result = await sync_customer(...)
    
    # Assert: Verify behavior
    assert result.success is True
```

## API Rate Limits

### Shopify
- **REST API**: 2 calls per second (40/min bucket)
- **Strategy**: Add 0.5s delay between calls
- **Headers**: `X-Shopify-Shop-Api-Call-Limit` shows usage

### Xero
- **Rate Limit**: 60 calls per minute per tenant
- **Daily Limit**: 5000 calls per day per tenant (we're well under)
- **Strategy**: Track calls, sleep if approaching limit
- **Headers**: `X-Rate-Limit-Remaining` shows usage

## Environment Variables

### Required
```bash
# Shopify Configuration
SHOPIFY_SHOP_URL=https://your-store.myshopify.com
SHOPIFY_API_KEY=shpat_xxxxxxxxxxxxx
SHOPIFY_API_SECRET=shpss_xxxxxxxxxxxxx
SHOPIFY_ACCESS_TOKEN=shpat_xxxxxxxxxxxxx

# Xero Configuration
XERO_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
XERO_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
XERO_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

### Optional
```bash
# Application Settings
LOG_LEVEL=INFO                    # DEBUG, INFO, WARNING, ERROR
DRY_RUN=false                     # true = don't actually update Xero
DATABASE_PATH=data/sync.db        # SQLite database location
LOG_FILE=logs/sync.log            # Log file location

# Performance Tuning
MAX_RETRIES=3                     # Max retry attempts for failed API calls
RETRY_DELAY=2                     # Initial retry delay in seconds
RATE_LIMIT_BUFFER=5               # Stay 5 calls under rate limit
```

## Checksum Calculation

Checksums detect changes efficiently without comparing every field.

### Customer Checksum
```python
def calculate_customer_checksum(customer: ShopifyCustomer) -> str:
    """Include fields that matter for Xero contact"""
    data = (
        f"{customer.email}|"
        f"{customer.first_name}|"
        f"{customer.last_name}|"
        f"{customer.phone}|"
        f"{customer.default_address.address1 if customer.default_address else ''}"
    )
    return hashlib.sha256(data.encode()).hexdigest()
```

### Product Checksum
```python
def calculate_product_checksum(product: ShopifyProduct) -> str:
    """Include fields that matter for Xero item"""
    data = (
        f"{product.title}|"
        f"{product.vendor}|"
        f"{product.product_type}|"
        f"{product.variants[0].price}|"
        f"{product.variants[0].sku}"
    )
    return hashlib.sha256(data.encode()).hexdigest()
```

## Duplicate Prevention Strategy

### Customers
- **Primary Key**: Email address
- **Check**: Before creating Xero contact, search by email
- **Action**: If exists, link to existing; if not, create new

### Products
- **Primary Key**: SKU (Stock Keeping Unit)
- **Check**: Before creating Xero item, search by SKU
- **Action**: If exists, link to existing; if not, create new

### Orders
- **Primary Key**: Shopify order number in Xero invoice reference
- **Check**: Before creating Xero invoice, search by reference
- **Action**: If exists, link to existing; if not, create new

## Common Development Tasks

### Run Sync Locally
```bash
# One-time sync
docker-compose run --rm shopify-xero-sync

# Dry-run mode (don't update Xero)
docker-compose run --rm -e DRY_RUN=true shopify-xero-sync

# Debug mode with verbose logging
docker-compose run --rm -e LOG_LEVEL=DEBUG shopify-xero-sync
```

### Run Tests
```bash
# All tests
docker-compose run --rm shopify-xero-sync pytest

# With coverage
docker-compose run --rm shopify-xero-sync pytest --cov=src --cov-report=html

# Specific test file
docker-compose run --rm shopify-xero-sync pytest tests/unit/test_sync_engine.py

# Run tests locally (without Docker)
pytest -v
```

### Inspect Database
```bash
# Open SQLite shell
sqlite3 data/sync.db

# Check mappings
SELECT entity_type, COUNT(*) FROM sync_mappings GROUP BY entity_type;

# Check recent sync history
SELECT * FROM sync_history ORDER BY started_at DESC LIMIT 5;

# Check errors
SELECT * FROM sync_errors WHERE occurred_at > datetime('now', '-1 day');
```

### View Logs
```bash
# Tail live logs
tail -f logs/sync.log

# Search for errors
grep ERROR logs/sync.log

# View last 100 lines
tail -n 100 logs/sync.log
```

### Rebuild Database
```bash
# Delete SQLite database
rm data/sync.db

# Run sync - will rebuild mappings
docker-compose run --rm shopify-xero-sync
```

## Security Considerations

### Secrets Management
- **Never commit**: .env files in .gitignore
- **Environment variables only**: No hardcoded credentials
- **Token rotation**: Xero tokens expire, must refresh
- **Least privilege**: Use minimal API scopes required

### API Security
- **HTTPS only**: All API calls over TLS
- **Token storage**: If persisting, encrypt OAuth tokens
- **Logging**: Never log tokens, credentials, or PII
- **Validation**: Validate all data from APIs

### Container Security
- **Non-root user**: Container runs as UID 1000
- **Read-only**: Root filesystem read-only where possible
- **Minimal image**: Use Alpine/slim base, minimal packages
- **Vulnerability scanning**: Scan with Trivy regularly

## Troubleshooting

### Problem: "Authentication failed"
```bash
# Check environment variables are set
docker-compose run --rm shopify-xero-sync env | grep SHOPIFY
docker-compose run --rm shopify-xero-sync env | grep XERO

# Verify tokens haven't expired
# Xero tokens expire after 30 minutes - need refresh
```

### Problem: "Rate limit exceeded"
```bash
# Check how many calls made
grep "Rate limit" logs/sync.log

# Increase delays between calls
# Edit RETRY_DELAY in .env
```

### Problem: "Duplicate records created"
```bash
# Check for missing email/SKU in entities
sqlite3 data/sync.db "SELECT * FROM sync_mappings WHERE entity_type='customer';"

# Verify duplicate detection logic
# Look for Xero entities without mapped Shopify IDs
```

### Problem: "SQLite database locked"
```bash
# Check if another sync is running
ps aux | grep sync.py

# Kill stuck process
pkill -f sync.py

# If corrupted, rebuild
rm data/sync.db && docker-compose run --rm shopify-xero-sync
```

## Future Enhancements

### Phase 2 (After MVP)
- [ ] Product variants handling (different sizes/colors)
- [ ] Inventory quantity sync
- [ ] Refund/return handling
- [ ] Multi-currency support
- [ ] Webhook support for real-time sync

### Phase 3 (Scale Up)
- [ ] Migrate to AWS Lambda for scheduled execution
- [ ] Use DynamoDB instead of SQLite
- [ ] Add CloudWatch monitoring
- [ ] Implement SQS for async processing
- [ ] Add SNS alerts for failures

### Phase 4 (Polish)
- [ ] Web dashboard for sync status
- [ ] Manual sync trigger via API
- [ ] Conflict resolution UI
- [ ] Sync analytics and reporting

## Sub-Agent Usage Guide

This project uses specialized Claude Code sub-agents for different aspects:

- **@integration-architect**: Core sync logic, API clients, architecture decisions
- **@test-engineer**: Writing tests, test fixtures, coverage analysis
- **@security-auditor**: Security review, vulnerability scanning, secrets management
- **@docker-devops-engineer**: Dockerfile optimization, container security, deployment
- **@qa-integration-tester**: End-to-end testing, validation, user documentation

### When to Use Which Agent

**Starting new feature**:
```
@integration-architect - I need to add support for syncing product variants
```

**After building feature**:
```
@test-engineer - Please add comprehensive tests for product variant sync
@security-auditor - Review the new product variant code for security issues
```

**Docker/deployment changes**:
```
@docker-devops-engineer - Optimize the Dockerfile to reduce image size
```

**Final validation**:
```
@qa-integration-tester - Create test scenarios for product variant sync and validate end-to-end
```

## Resources

### API Documentation
- [Shopify REST Admin API](https://shopify.dev/docs/api/admin-rest)
- [Xero API Documentation](https://developer.xero.com/documentation/)
- [Xero OAuth2 Guide](https://developer.xero.com/documentation/guides/oauth2/overview/)

### Python Libraries
- [httpx](https://www.python-httpx.org/) - HTTP client
- [Pydantic](https://docs.pydantic.dev/) - Data validation
- [pytest](https://docs.pytest.org/) - Testing framework

### Tools
- [Postman Collection for Xero](https://developer.xero.com/documentation/guides/oauth2/postman/)
- [Shopify GraphiQL](https://shopify.dev/docs/api/admin-graphql) - API explorer

## Contact & Support

**Project Owner**: Adam
**Purpose**: Halyrd business accounting automation
**Repository**: [Add Git URL when created]

## License

[To be determined - probably MIT or Apache 2.0 for open source]

---

*This document is maintained by Claude Code and should be updated as the project evolves.*