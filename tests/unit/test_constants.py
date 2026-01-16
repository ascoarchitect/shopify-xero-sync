"""Unit tests for constants and GL code mappings.

Tests verify that:
- GL code mappings are defined correctly
- Category lookups work with case-insensitive matching
- Default values are returned for unknown categories
- Tax types are defined correctly
"""

import pytest

from src.constants import (
    GLCodeMapping,
    CATEGORY_GL_MAPPING,
    DEFAULT_GL_MAPPING,
    get_gl_codes_for_category,
    TAX_TYPE_STANDARD,
    TAX_TYPE_REDUCED,
    TAX_TYPE_ZERO,
    TAX_TYPE_EXEMPT,
    TAX_TYPE_NO_VAT,
    DEFAULT_TAX_TYPE,
    DEFAULT_PAYMENT_TERMS_DAYS,
    INVOICE_REFERENCE_PREFIX,
    DEFAULT_LINE_ITEM_ACCOUNT,
)


class TestGLCodeMapping:
    """Tests for GLCodeMapping namedtuple."""

    def test_gl_code_mapping_structure(self):
        """Test GLCodeMapping has expected fields."""
        mapping = GLCodeMapping(
            sales_account="200",
            purchase_account="310",
            description="Test Product",
        )

        assert mapping.sales_account == "200"
        assert mapping.purchase_account == "310"
        assert mapping.description == "Test Product"

    def test_gl_code_mapping_is_namedtuple(self):
        """Test GLCodeMapping behaves like a namedtuple."""
        mapping = GLCodeMapping("200", "310", "Test")

        # Should be immutable
        with pytest.raises(AttributeError):
            mapping.sales_account = "201"


class TestCategoryGLMapping:
    """Tests for CATEGORY_GL_MAPPING dictionary."""

    def test_wax_melts_category(self):
        """Test wax melts category is mapped."""
        mapping = CATEGORY_GL_MAPPING["wax melts"]

        assert mapping.sales_account == "200"
        assert mapping.purchase_account == "310"

    def test_candles_category(self):
        """Test candles category is mapped."""
        mapping = CATEGORY_GL_MAPPING["candles"]

        assert mapping.sales_account == "200"
        assert mapping.purchase_account == "310"

    def test_gifts_category(self):
        """Test gifts category is mapped."""
        mapping = CATEGORY_GL_MAPPING["gifts"]

        assert mapping.sales_account == "200"

    def test_gift_sets_category(self):
        """Test gift sets category is mapped."""
        mapping = CATEGORY_GL_MAPPING["gift sets"]

        assert mapping.sales_account == "200"

    def test_accessories_category(self):
        """Test accessories category is mapped."""
        mapping = CATEGORY_GL_MAPPING["accessories"]

        assert mapping.sales_account == "200"

    def test_samples_category(self):
        """Test samples category uses different account."""
        mapping = CATEGORY_GL_MAPPING["samples"]

        assert mapping.sales_account == "260"  # Other Revenue
        assert mapping.purchase_account == "310"

    def test_seasonal_categories(self):
        """Test seasonal categories are mapped."""
        assert "seasonal" in CATEGORY_GL_MAPPING
        assert "christmas" in CATEGORY_GL_MAPPING
        assert "valentines" in CATEGORY_GL_MAPPING

    def test_all_categories_lowercase(self):
        """Test all category keys are lowercase."""
        for key in CATEGORY_GL_MAPPING.keys():
            assert key == key.lower()


class TestDefaultGLMapping:
    """Tests for DEFAULT_GL_MAPPING."""

    def test_default_mapping_exists(self):
        """Test default mapping is defined."""
        assert DEFAULT_GL_MAPPING is not None

    def test_default_mapping_structure(self):
        """Test default mapping has expected values."""
        assert DEFAULT_GL_MAPPING.sales_account == "200"
        assert DEFAULT_GL_MAPPING.purchase_account == "310"
        assert "Uncategorized" in DEFAULT_GL_MAPPING.description


class TestGetGLCodesForCategory:
    """Tests for get_gl_codes_for_category function."""

    def test_exact_match(self):
        """Test exact lowercase match."""
        result = get_gl_codes_for_category("wax melts")

        assert result.sales_account == "200"

    def test_case_insensitive_uppercase(self):
        """Test uppercase category name."""
        result = get_gl_codes_for_category("WAX MELTS")

        assert result.sales_account == "200"

    def test_case_insensitive_mixed_case(self):
        """Test mixed case category name."""
        result = get_gl_codes_for_category("Wax Melts")

        assert result.sales_account == "200"

    def test_whitespace_trimming(self):
        """Test whitespace is trimmed."""
        result = get_gl_codes_for_category("  wax melts  ")

        assert result.sales_account == "200"

    def test_unknown_category_returns_default(self):
        """Test unknown category returns default mapping."""
        result = get_gl_codes_for_category("unknown category")

        assert result == DEFAULT_GL_MAPPING

    def test_none_category_returns_default(self):
        """Test None category returns default mapping."""
        result = get_gl_codes_for_category(None)

        assert result == DEFAULT_GL_MAPPING

    def test_empty_string_returns_default(self):
        """Test empty string returns default mapping."""
        result = get_gl_codes_for_category("")

        assert result == DEFAULT_GL_MAPPING

    def test_samples_returns_different_account(self):
        """Test samples category returns different account code."""
        result = get_gl_codes_for_category("Samples")

        assert result.sales_account == "260"  # Other Revenue

    def test_all_mapped_categories(self):
        """Test all mapped categories return valid mappings."""
        for category in CATEGORY_GL_MAPPING.keys():
            result = get_gl_codes_for_category(category)
            assert result.sales_account is not None
            assert result.purchase_account is not None


class TestTaxTypes:
    """Tests for tax type constants."""

    def test_standard_tax_type(self):
        """Test standard VAT tax type."""
        assert TAX_TYPE_STANDARD == "OUTPUT2"

    def test_reduced_tax_type(self):
        """Test reduced VAT tax type."""
        assert TAX_TYPE_REDUCED == "OUTPUT"

    def test_zero_rated_tax_type(self):
        """Test zero-rated tax type."""
        assert TAX_TYPE_ZERO == "ZERORATEDOUTPUT"

    def test_exempt_tax_type(self):
        """Test exempt tax type."""
        assert TAX_TYPE_EXEMPT == "EXEMPTOUTPUT"

    def test_no_vat_tax_type(self):
        """Test no VAT tax type."""
        assert TAX_TYPE_NO_VAT == "NONE"

    def test_default_tax_type(self):
        """Test default tax type is standard."""
        assert DEFAULT_TAX_TYPE == TAX_TYPE_STANDARD


class TestInvoiceSettings:
    """Tests for invoice settings constants."""

    def test_payment_terms(self):
        """Test default payment terms."""
        assert DEFAULT_PAYMENT_TERMS_DAYS == 0  # Due immediately

    def test_invoice_reference_prefix(self):
        """Test invoice reference prefix."""
        assert INVOICE_REFERENCE_PREFIX == "SHOP-"

    def test_line_item_account(self):
        """Test default line item account."""
        assert DEFAULT_LINE_ITEM_ACCOUNT == "200"


class TestGLCodeConsistency:
    """Tests for GL code consistency across categories."""

    def test_all_sales_accounts_are_strings(self):
        """Test all sales accounts are string type."""
        for category, mapping in CATEGORY_GL_MAPPING.items():
            assert isinstance(mapping.sales_account, str), f"{category} sales_account is not string"

    def test_all_purchase_accounts_are_strings(self):
        """Test all purchase accounts are string type."""
        for category, mapping in CATEGORY_GL_MAPPING.items():
            assert isinstance(mapping.purchase_account, str), f"{category} purchase_account is not string"

    def test_all_descriptions_are_strings(self):
        """Test all descriptions are string type."""
        for category, mapping in CATEGORY_GL_MAPPING.items():
            assert isinstance(mapping.description, str), f"{category} description is not string"

    def test_account_codes_are_numeric_strings(self):
        """Test account codes contain only digits."""
        for category, mapping in CATEGORY_GL_MAPPING.items():
            assert mapping.sales_account.isdigit(), f"{category} sales_account is not numeric"
            assert mapping.purchase_account.isdigit(), f"{category} purchase_account is not numeric"
