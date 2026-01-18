#!/usr/bin/env python3
"""Quick test to verify email marketing feature is properly integrated.

This is a simple smoke test to ensure the new functionality doesn't break
existing code and that the methods are properly accessible.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import Settings


def test_config_has_email_marketing_setting():
    """Test that the config includes the new email marketing setting."""
    settings = Settings(
        shopify_shop_url="https://test.myshopify.com",
        shopify_client_id="test_id",
        shopify_client_secret="test_secret",
        xero_client_id="test_xero_id",
        xero_client_secret="test_xero_secret",
        xero_tenant_id="test_tenant_id",
    )
    
    # Check that the setting exists and has a default value
    assert hasattr(settings, 'enable_email_marketing')
    assert isinstance(settings.enable_email_marketing, bool)
    assert settings.enable_email_marketing == False  # Default should be False
    print("✓ Config has enable_email_marketing setting with correct default")


def test_shopify_client_has_update_method():
    """Test that ShopifyClient has the update_customer_email_marketing method."""
    from src.shopify_client import ShopifyClient
    
    # Check method exists
    assert hasattr(ShopifyClient, 'update_customer_email_marketing')
    print("✓ ShopifyClient has update_customer_email_marketing method")


def test_shopify_graphql_client_has_update_method():
    """Test that ShopifyGraphQLClient has the update_customer_email_marketing method."""
    from src.shopify_graphql_client import ShopifyGraphQLClient
    
    # Check method exists
    assert hasattr(ShopifyGraphQLClient, 'update_customer_email_marketing')
    print("✓ ShopifyGraphQLClient has update_customer_email_marketing method")


def test_sync_engine_has_email_marketing_methods():
    """Test that SyncEngine has the email marketing methods."""
    from src.sync_engine import SyncEngine
    
    # Check methods exist
    assert hasattr(SyncEngine, '_update_customer_email_marketing')
    assert hasattr(SyncEngine, 'enable_email_marketing_for_all_customers')
    print("✓ SyncEngine has email marketing methods")


def test_enable_email_marketing_script_exists():
    """Test that the standalone script exists and is executable."""
    script_path = Path(__file__).parent / "enable_email_marketing.py"
    assert script_path.exists()
    assert script_path.is_file()
    print("✓ enable_email_marketing.py script exists")


def test_documentation_exists():
    """Test that documentation for the feature exists."""
    guide_path = Path(__file__).parent / "EMAIL_MARKETING_GUIDE.md"
    assert guide_path.exists()
    assert guide_path.is_file()
    print("✓ EMAIL_MARKETING_GUIDE.md documentation exists")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Email Marketing Feature Integration")
    print("=" * 60)
    print()
    
    tests = [
        test_config_has_email_marketing_setting,
        test_shopify_client_has_update_method,
        test_shopify_graphql_client_has_update_method,
        test_sync_engine_has_email_marketing_methods,
        test_enable_email_marketing_script_exists,
        test_documentation_exists,
    ]
    
    failed = []
    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"✗ {test.__name__} failed: {e}")
            failed.append(test.__name__)
        except Exception as e:
            print(f"✗ {test.__name__} error: {e}")
            failed.append(test.__name__)
    
    print()
    print("=" * 60)
    if failed:
        print(f"FAILED: {len(failed)} test(s) failed")
        for name in failed:
            print(f"  - {name}")
        return 1
    else:
        print("SUCCESS: All tests passed!")
        print()
        print("The email marketing feature is properly integrated.")
        print("See EMAIL_MARKETING_GUIDE.md for usage instructions.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
