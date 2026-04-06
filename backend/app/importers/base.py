from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import ClassVar, Protocol, Optional, Any


@dataclass
class ValidationResult:
    """Result of importer validation.
    
    Attributes:
        is_valid: True if validation passed, False otherwise
        errors: List of user-facing error messages
        required_inputs: Dict of helpful hints for user input correction, 
                        e.g. {"required_months": ["2025-03"], "provided_months": ["2025-01"]}
    """
    is_valid: bool
    errors: list[str] = field(default_factory=list)  # User-facing error messages
    required_inputs: dict[str, Any] = field(default_factory=dict)  # Hints for user, e.g., {"required_months": ["2025-03"]}


@dataclass
class ParsedTransaction:
    """Represents a single parsed transaction from an import source."""
    source: str                    # "zerodha", "nps", "cas"
    asset_name: str                # human-readable name
    asset_identifier: str          # ISIN for stocks, scheme name for NPS
    asset_type: str                # "STOCK_IN", "NPS", "MF", etc.
    txn_type: str                  # "BUY", "SELL", "CONTRIBUTION", etc.
    date: date
    units: Optional[float] = None
    price_per_unit: Optional[float] = None
    amount_inr: float = 0.0       # signed: negative=outflow, positive=inflow
    charges_inr: float = 0.0
    txn_id: str = ""               # unique, either native or SHA-256 hash
    lot_id: Optional[str] = None
    notes: Optional[str] = None
    # Extra metadata for asset creation
    isin: Optional[str] = None
    exchange: Optional[str] = None
    mfapi_scheme_code: Optional[str] = None
    scheme_category: Optional[str] = None
    asset_class: Optional[str] = None     # e.g. "EQUITY", "DEBT" — overrides ASSET_CLASS_MAP if set
    forex_rate: Optional[float] = None    # USD/INR rate used for conversion
    # Fidelity PDF acquisition metadata — used by FidelityPreCommitProcessor
    acquisition_date: Optional[date] = None        # date_acquired from Fidelity PDF sale row
    acquisition_cost: Optional[float] = None       # cost basis in INR (cost_usd * acquisition_forex_rate)
    acquisition_forex_rate: Optional[float] = None # USD/INR rate at acquisition date


@dataclass
class ParsedFundSnapshot:
    """Closing balance summary extracted from a CAS PDF per fund."""
    isin: str
    asset_name: str
    date: date                  # NAV date from CAS
    closing_units: float
    nav_price_inr: float        # INR per unit (not paise)
    market_value_inr: float     # total INR
    total_cost_inr: float       # cost basis INR


@dataclass
class ImportResult:
    """Result of parsing a file."""
    source: str
    transactions: list[ParsedTransaction] = field(default_factory=list)
    snapshots: list[ParsedFundSnapshot] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duplicate_count: int = 0
    closing_valuation_inr: Optional[float] = None
    closing_valuation_date: Optional[date] = None
    closing_valuation_source: Optional[str] = None
    closing_valuation_notes: Optional[str] = None


class LegacyBaseImporter(Protocol):
    def parse(self, file_bytes: bytes, filename: str = "") -> ImportResult: ...


class BaseImporter(ABC):
    """
    Abstract base class for all file importers.

    Class variables (must be set on each concrete subclass):
        source:     identifier string, e.g. "zerodha", "cas", "groww"
        asset_type: string asset type, e.g. "STOCK_IN", "MF"
        format:     file format, e.g. "csv", "pdf"

    Adding a new provider: create a new subclass, decorate with @register_importer.
    No other files need to change.
    """
    source: ClassVar[str]
    asset_type: ClassVar[str]
    format: ClassVar[str]

    @abstractmethod
    def parse(self, file_bytes: bytes) -> "ImportResult": ...

    def validate(self, result: "ImportResult") -> ValidationResult:
        """Post-parse validation hook. Default: always passes. Override for custom checks.
        
        This method is called after parse() completes. Subclasses can override to validate
        parsed results or check for required inputs (e.g., exchange_rates completeness).
        
        Args:
            result: ImportResult from parse()
        
        Returns:
            ValidationResult with is_valid, errors, and optional required_inputs hints
        """
        return ValidationResult(is_valid=True, errors=[], required_inputs={})
