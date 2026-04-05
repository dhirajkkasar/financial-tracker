"""Helper for validating exchange rates in Fidelity importers."""
import json as _json
from app.importers.base import ImportResult, ValidationResult


class ExchangeRateValidationHelper:
    """Helper class for validating exchange_rates in Fidelity importers.
    
    Provides methods to parse, validate structure, and check completeness
    of exchange rates required for currency conversion during imports.
    """

    @staticmethod
    def validate_exchange_rates(result: ImportResult, exchange_rates: dict[str, float]) -> ValidationResult:
        """Post-parse validation: verify exchange_rates completeness and structure.
        
        Args:
            result: ImportResult from parse()
            exchange_rates: Dict mapping "YYYY-MM" strings to exchange rates (USD/INR floats)
        
        Returns:
            ValidationResult with errors if exchange_rates missing or invalid for required months
        """
        if exchange_rates is None:
            return ValidationResult(
                is_valid=False,
                errors=['exchange_rates must be valid JSON, e.g. {"2025-03": 86.5}'],
                required_inputs={}
            )
        
        # Validate structure
        validation_error = ExchangeRateValidationHelper._validate_exchange_rates_structure(exchange_rates)
        if validation_error:
            return ValidationResult(
                is_valid=False,
                errors=[validation_error],
                required_inputs={}
            )
        
        # Extract required months from parsed transactions
        required_months = ExchangeRateValidationHelper._extract_required_months(result)
        
        # Check completeness
        missing = sorted([m for m in required_months if m not in exchange_rates])
        if missing:
            return ValidationResult(
                is_valid=False,
                errors=[f"Missing exchange_rates for months: {', '.join(missing)}"],
                required_inputs={
                    "required_months": sorted(required_months),
                    "provided_months": sorted(exchange_rates.keys()),
                }
            )
        
        return ValidationResult(is_valid=True, errors=[], required_inputs={})

    @staticmethod
    def parse_exchange_rates_json(exchange_rates: str) -> dict[str, float] | None:
        """Parse exchange_rates from JSON string to dict.
        
        Args:
            exchange_rates: JSON string of exchange_rates, e.g. '{"2025-03": 86.5}'
        
        Returns:
            Parsed dict mapping "YYYY-MM" to float, or None if parsing fails
        """
        try:
            return _json.loads(exchange_rates)
        except Exception:
            print("Failed to parse exchange_rates JSON:", exchange_rates)
            return None

    @staticmethod
    def _validate_exchange_rates_structure(exchange_rates: dict) -> str | None:
        """Validate that exchange_rates has correct structure.
        
        Args:
            exchange_rates: dict to validate
        
        Returns:
            Error message (str) if invalid structure, None if valid
        """
        if not isinstance(exchange_rates, dict):
            return 'exchange_rates must be a dictionary, e.g. {"2025-03": 86.5}'
        
        if not all(isinstance(v, (int, float)) for v in exchange_rates.values()):
            return 'exchange_rates values must be numbers, e.g. {"2025-03": 86.5}'
        
        return None

    @staticmethod
    def _extract_required_months(result: ImportResult) -> list[str]:
        """Extract unique YYYY-MM strings from all parsed transactions.
        
        Args:
            result: ImportResult containing transactions
        
        Returns:
            Sorted list of unique required month-year strings
        """
        required_months: set[str] = set()
        for txn in result.transactions:
            required_months.add(txn.date.strftime("%Y-%m"))
        return sorted(required_months)
