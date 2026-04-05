"""Unit tests for ExchangeRateValidationHelper."""
import pytest
from app.importers.base import ImportResult, ParsedTransaction, ValidationResult
from app.importers.helpers import ExchangeRateValidationHelper
from datetime import date


class TestExchangeRateValidationHelper:
    """Test ExchangeRateValidationHelper class."""

    def test_validate_exchange_rates_with_valid_rates(self):
        """Validation passes when exchange_rates dict is valid and complete."""
        # Create a result with transactions for 2025-03 and 2024-09
        txn1 = ParsedTransaction(
            source="test",
            asset_name="TEST",
            asset_identifier="TEST",
            asset_type="STOCK",
            txn_type="BUY",
            date=date(2025, 3, 17)
        )
        txn2 = ParsedTransaction(
            source="test",
            asset_name="TEST",
            asset_identifier="TEST",
            asset_type="STOCK",
            txn_type="BUY",
            date=date(2024, 9, 15)
        )
        result = ImportResult(source="test", transactions=[txn1, txn2])
        
        exchange_rates = {"2025-03": 86.5, "2024-09": 83.8}
        validation_result = ExchangeRateValidationHelper.validate_exchange_rates(result, exchange_rates)
        
        assert validation_result.is_valid is True
        assert validation_result.errors == []

    def test_validate_exchange_rates_with_non_dict_type(self):
        """Validation fails when exchange_rates is not a dict."""
        txn = ParsedTransaction(
            source="test",
            asset_name="TEST",
            asset_identifier="TEST",
            asset_type="STOCK",
            txn_type="BUY",
            date=date(2025, 3, 17)
        )
        result = ImportResult(source="test", transactions=[txn])
        
        # Pass a string or list instead of dict
        validation_result = ExchangeRateValidationHelper.validate_exchange_rates(result, "not a dict")
        
        assert validation_result.is_valid is False
        assert len(validation_result.errors) > 0
        assert "dictionary" in validation_result.errors[0]

    def test_validate_exchange_rates_with_non_numeric_values(self):
        """Validation fails when exchange_rates values are not numeric."""
        txn = ParsedTransaction(
            source="test",
            asset_name="TEST",
            asset_identifier="TEST",
            asset_type="STOCK",
            txn_type="BUY",
            date=date(2025, 3, 17)
        )
        result = ImportResult(source="test", transactions=[txn])
        
        exchange_rates = {"2025-03": "abc"}
        validation_result = ExchangeRateValidationHelper.validate_exchange_rates(result, exchange_rates)
        
        assert validation_result.is_valid is False
        assert len(validation_result.errors) > 0
        assert "numbers" in validation_result.errors[0]

    def test_validate_exchange_rates_with_missing_months(self):
        """Validation fails when required months are missing from exchange_rates."""
        txn1 = ParsedTransaction(
            source="test",
            asset_name="TEST",
            asset_identifier="TEST",
            asset_type="STOCK",
            txn_type="BUY",
            date=date(2025, 3, 17)
        )
        txn2 = ParsedTransaction(
            source="test",
            asset_name="TEST",
            asset_identifier="TEST",
            asset_type="STOCK",
            txn_type="BUY",
            date=date(2024, 9, 15)
        )
        result = ImportResult(source="test", transactions=[txn1, txn2])
        
        # Missing 2024-09
        exchange_rates = {"2025-03": 86.5}
        validation_result = ExchangeRateValidationHelper.validate_exchange_rates(result, exchange_rates)
        
        assert validation_result.is_valid is False
        assert len(validation_result.errors) > 0
        assert "Missing exchange_rates" in validation_result.errors[0]
        assert "2024-09" in validation_result.errors[0]
        assert validation_result.required_inputs["required_months"] == ["2024-09", "2025-03"]
        assert validation_result.required_inputs["provided_months"] == ["2025-03"]

    def test_validate_exchange_rates_with_no_transactions_and_no_exchange_rates(self):
        """Validation passes when there are no transactions and no exchange_rates."""
        result = ImportResult(source="test", transactions=[])
        
        validation_result = ExchangeRateValidationHelper.validate_exchange_rates(result, {})
        
        assert validation_result.is_valid is True
        assert validation_result.errors == []

    def test_validate_exchange_rates_with_no_exchange_rates_but_transactions(self):
        """Validation fails when there are transactions but no exchange_rates provided."""
        txn = ParsedTransaction(
            source="test",
            asset_name="TEST",
            asset_identifier="TEST",
            asset_type="STOCK",
            txn_type="BUY",
            date=date(2025, 3, 17)
        )
        result = ImportResult(source="test", transactions=[txn])
        
        # Empty exchange_rates dict
        validation_result = ExchangeRateValidationHelper.validate_exchange_rates(result, {})
        
        assert validation_result.is_valid is False
        assert len(validation_result.errors) > 0
        assert "Missing exchange_rates" in validation_result.errors[0]
        assert "2025-03" in validation_result.errors[0]

    def test_validate_exchange_rates_with_non_dict_type_list(self):
        """Validation fails when exchange_rates is a list instead of dict."""
        txn = ParsedTransaction(
            source="test",
            asset_name="TEST",
            asset_identifier="TEST",
            asset_type="STOCK",
            txn_type="BUY",
            date=date(2025, 3, 17)
        )
        result = ImportResult(source="test", transactions=[txn])
        
        # List instead of dict
        validation_result = ExchangeRateValidationHelper.validate_exchange_rates(result, ["2025-03", 86.5])
        
        assert validation_result.is_valid is False
        assert len(validation_result.errors) > 0
        assert "dictionary" in validation_result.errors[0]

    def test_validate_exchange_rates_with_extra_months(self):
        """Validation passes when more exchange_rates are provided than needed."""
        txn = ParsedTransaction(
            source="test",
            asset_name="TEST",
            asset_identifier="TEST",
            asset_type="STOCK",
            txn_type="BUY",
            date=date(2025, 3, 17)
        )
        result = ImportResult(source="test", transactions=[txn])
        
        # Provide extra months
        exchange_rates = {"2025-03": 86.5, "2024-09": 83.8, "2025-06": 85.0}
        validation_result = ExchangeRateValidationHelper.validate_exchange_rates(result, exchange_rates)
        
        assert validation_result.is_valid is True
        assert validation_result.errors == []

    def test_parse_exchange_rates_json_valid(self):
        """_parse_exchange_rates_json correctly parses valid JSON."""
        user_inputs = '{"2025-03": 86.5, "2024-09": 83.8}'
        result = ExchangeRateValidationHelper.parse_exchange_rates_json(user_inputs)
        
        assert result == {"2025-03": 86.5, "2024-09": 83.8}

    def test_parse_exchange_rates_json_invalid(self):
        """_parse_exchange_rates_json returns None for invalid JSON strings."""
        user_inputs = '{invalid json}'
        result = ExchangeRateValidationHelper.parse_exchange_rates_json(user_inputs)
        
        assert result is None

    def test_parse_exchange_rates_json_empty_dict(self):
        """_parse_exchange_rates_json can parse empty dict from JSON string."""
        user_inputs = '{}'
        result = ExchangeRateValidationHelper.parse_exchange_rates_json(user_inputs)
        
        assert result == {}

    def test_validate_exchange_rates_structure_valid_dict(self):
        """_validate_exchange_rates_structure accepts valid dict."""
        exchange_rates = {"2025-03": 86.5, "2024-09": 83.8}
        result = ExchangeRateValidationHelper._validate_exchange_rates_structure(exchange_rates)
        
        assert result is None

    def test_validate_exchange_rates_structure_valid_integers(self):
        """_validate_exchange_rates_structure accepts integer values."""
        exchange_rates = {"2025-03": 86, "2024-09": 83}
        result = ExchangeRateValidationHelper._validate_exchange_rates_structure(exchange_rates)
        
        assert result is None

    def test_validate_exchange_rates_structure_invalid_non_dict(self):
        """_validate_exchange_rates_structure rejects non-dict."""
        exchange_rates = ["2025-03", 86.5]
        result = ExchangeRateValidationHelper._validate_exchange_rates_structure(exchange_rates)
        
        assert result is not None
        assert "dictionary" in result

    def test_validate_exchange_rates_structure_invalid_non_numeric_values(self):
        """_validate_exchange_rates_structure rejects non-numeric values."""
        exchange_rates = {"2025-03": "86.5"}
        result = ExchangeRateValidationHelper._validate_exchange_rates_structure(exchange_rates)
        
        assert result is not None
        assert "numbers" in result

    def test_validate_exchange_rates_structure_invalid_mixed_types(self):
        """_validate_exchange_rates_structure rejects mixed types in values."""
        exchange_rates = {"2025-03": 86.5, "2024-09": "83.8"}
        result = ExchangeRateValidationHelper._validate_exchange_rates_structure(exchange_rates)
        
        assert result is not None
        assert "numbers" in result

    def test_extract_required_months_single_month(self):
        """_extract_required_months returns single month."""
        txn = ParsedTransaction(
            source="test",
            asset_name="TEST",
            asset_identifier="TEST",
            asset_type="STOCK",
            txn_type="BUY",
            date=date(2025, 3, 17)
        )
        result = ImportResult(source="test", transactions=[txn])
        
        months = ExchangeRateValidationHelper._extract_required_months(result)
        
        assert months == ["2025-03"]

    def test_extract_required_months_multiple_months(self):
        """_extract_required_months returns sorted unique months."""
        txn1 = ParsedTransaction(
            source="test",
            asset_name="TEST",
            asset_identifier="TEST",
            asset_type="STOCK",
            txn_type="BUY",
            date=date(2024, 9, 15)
        )
        txn2 = ParsedTransaction(
            source="test",
            asset_name="TEST",
            asset_identifier="TEST",
            asset_type="STOCK",
            txn_type="BUY",
            date=date(2025, 3, 17)
        )
        txn3 = ParsedTransaction(
            source="test",
            asset_name="TEST",
            asset_identifier="TEST",
            asset_type="STOCK",
            txn_type="BUY",
            date=date(2025, 3, 20)  # Same month as txn2
        )
        result = ImportResult(source="test", transactions=[txn1, txn2, txn3])
        
        months = ExchangeRateValidationHelper._extract_required_months(result)
        
        assert months == ["2024-09", "2025-03"]

    def test_extract_required_months_empty(self):
        """_extract_required_months returns empty list for no transactions."""
        result = ImportResult(source="test", transactions=[])
        
        months = ExchangeRateValidationHelper._extract_required_months(result)
        
        assert months == []

    def test_validate_exchange_rates_with_string_month_keys(self):
        """Validation handles month keys as strings in YYYY-MM format."""
        txn = ParsedTransaction(
            source="test",
            asset_name="TEST",
            asset_identifier="TEST",
            asset_type="STOCK",
            txn_type="BUY",
            date=date(2025, 3, 17)
        )
        result = ImportResult(source="test", transactions=[txn])
        
        # Month keys are strings in YYYY-MM format
        exchange_rates = {"2025-03": 86.5}
        validation_result = ExchangeRateValidationHelper.validate_exchange_rates(result, exchange_rates)
        
        assert validation_result.is_valid is True

    def test_validate_exchange_rates_multiple_missing_months(self):
        """Validation shows all missing months."""
        txn1 = ParsedTransaction(
            source="test",
            asset_name="TEST",
            asset_identifier="TEST",
            asset_type="STOCK",
            txn_type="BUY",
            date=date(2025, 1, 15)
        )
        txn2 = ParsedTransaction(
            source="test",
            asset_name="TEST",
            asset_identifier="TEST",
            asset_type="STOCK",
            txn_type="BUY",
            date=date(2025, 3, 17)
        )
        txn3 = ParsedTransaction(
            source="test",
            asset_name="TEST",
            asset_identifier="TEST",
            asset_type="STOCK",
            txn_type="BUY",
            date=date(2024, 9, 20)
        )
        result = ImportResult(source="test", transactions=[txn1, txn2, txn3])
        
        # Missing 2025-01 and 2024-09
        exchange_rates = {"2025-03": 86.5}
        validation_result = ExchangeRateValidationHelper.validate_exchange_rates(result, exchange_rates)
        
        assert validation_result.is_valid is False
        assert "2024-09" in validation_result.errors[0]
        assert "2025-01" in validation_result.errors[0]
