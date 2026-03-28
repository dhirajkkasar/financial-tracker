from typing import Protocol, runtime_checkable

from app.models.asset import AssetClass


def classify_mf(scheme_category: str | None) -> AssetClass:
    """Derive AssetClass from mfapi.in scheme_category string.

    Debt Scheme → DEBT.
    Everything else (Equity, Hybrid, Other, Solution Oriented, unknown) → EQUITY.
    """
    if not scheme_category:
        return AssetClass.EQUITY
    if scheme_category.lower().startswith("debt scheme"):
        return AssetClass.DEBT
    return AssetClass.EQUITY


# ---------------------------------------------------------------------------
# ISchemeClassifier protocol + DefaultSchemeClassifier wrapper
# ---------------------------------------------------------------------------

@runtime_checkable
class ISchemeClassifier(Protocol):
    """Classifies an MF scheme category string into an AssetClass."""
    def classify(self, scheme_category: str) -> AssetClass: ...


class DefaultSchemeClassifier:
    """Wraps the module-level classify_mf function for DI injection."""

    def classify(self, scheme_category: str) -> AssetClass:
        return classify_mf(scheme_category)
