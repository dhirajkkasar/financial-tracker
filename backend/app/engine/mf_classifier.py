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
