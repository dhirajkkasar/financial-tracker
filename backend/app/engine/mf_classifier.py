from typing import Protocol, runtime_checkable

import logging

from app.models.asset import AssetClass

logger = logging.getLogger(__name__)


def classify_mf(scheme_category: str | None) -> AssetClass:
    """Derive AssetClass from mfapi.in scheme_category string.

    Debt Scheme → DEBT.
    Hybrid conservative / debt-oriented (e.g. "Hybrid Scheme - Conservative Hybrid
    Fund") → DEBT (bond-heavy, taxed like debt).
    Debt-like keywords missed by the "Debt Scheme" prefix (liquid, money market,
    bond, gilt, credit, corporate) → DEBT.
    Everything else (Equity, other Hybrid, Other, Solution Oriented, unknown/None)
    → EQUITY (with a warning for unknown/None so misclassifications are visible).
    """
    if not scheme_category:
        logger.warning("classify_mf: empty/None scheme_category — defaulting to EQUITY")
        return AssetClass.EQUITY
    lowered = scheme_category.lower()
    if lowered.startswith("debt scheme"):
        return AssetClass.DEBT
    if "hybrid" in lowered and ("conservative" in lowered or "debt oriented" in lowered):
        return AssetClass.DEBT
    if any(kw in lowered for kw in ("liquid", "money market", "bond", "gilt", "credit", "corporate")):
        return AssetClass.DEBT
    if lowered.startswith(("equity scheme", "hybrid scheme", "other scheme", "solution oriented scheme")):
        return AssetClass.EQUITY
    logger.warning("classify_mf: unknown scheme_category %r — defaulting to EQUITY", scheme_category)
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
