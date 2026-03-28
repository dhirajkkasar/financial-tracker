"""Helper for validating exchange rates in Fidelity importers."""
import json as _json
from app.importers.base import ImportResult, ValidationResult


class ExchangeRateValidationHelper:
    """Helper class for validating exchange_rates in Fidelity importers.
    
    Provides methods to parse, validate structure, and check completeness
    of exchange rates required for currency conversion during imports.
    """

    @staticmethod
    def validate_exchange_rates(result: ImportResult, **kwargs) -> ValidationResult:
        """Post-parse validation: verify exchange_rates completeness.
        
        Args:
            result: ImportResult from parse()
            **kwargs: Should contain 'user_inputs' as JSON string of exchange_rates
        
        Returns:
            ValidationResult with errors if exchange_rates are missing for required months
        """
        # Get raw user_inputs (exchange_rates as JSON string) from kwargs
        user_inputs = kwargs.get("user_inputs")
        if not user_inputs:
            # No exchange_rates provided; if there are transactions, this is an error
            if result.transactions:
                return ValidationResult(
                    is_valid=False,
                    errors=["exchange_rates is required for fidelity imports"],
                    required_inputs={}
                )
            return ValidationResult(is_valid=True, errors=[], required_inputs={})
        
        # Parse user_inputs as JSON
        exchange_rates = ExchangeRateValidationHelper._parse_exchange_rates_json(user_inputs)
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
    def _parse_exchange_rates_json(user_inputs: str) -> dict[str, float] | None:
        """Parse exchange_rates from JSON string.
        
        Args:
            user_inputs: JSON string of exchange_rates, e.g. '{"2025-03": 86.5}'
        
        Returns:
            Parsed dict or None if parsing fails
        """
        try:
            return _json.loads(user_inputs)
        except Exception:
            return None

    @staticmethod
    def _validate_exchange_rates_structure(exchange_rates: dict) -> str | None:
        """Validate that exchange_rates has correct structure.
        
        Args:
            exchange_rates: dict to validate
        
        Returns:
            Error message if invalid, None if valid
        """
        if not isinstance(exchange_rates, dict):
            return 'exchange_rates must be a dictionary, e.g. {"2025-03": 86.5}'
        
        if not all(isinstance(v, (int, float)) for v in exchange_rates.values()):
            return 'exchange_rates values must be numbers, e.g. {"2025-03": 86.5}'
        
        return None

    @staticmethod
    def _extract_required_months(result: ImportResult) -> list[str]:
        """Extract unique YYYY-MM strings from parsed transactions.
        
        Args:
            result: ImportResult containing transactions
        
        Returns:
            Sorted list of required month-year strings
        """
        required_months: set[str] = set()
        for txn in result.transactions:
            required_months.add(txn.date.strftime("%Y-%m"))
        return sorted(required_months)
