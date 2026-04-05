# Import strategy modules to trigger registration.
# indian_equity, foreign_equity, gold, debt_mf are DELETED —
# their asset types are now handled by FifoTaxGainsStrategy registered in dependencies.py.
from app.services.tax.strategies import (  # noqa: F401
    accrued_interest,
    real_estate,
)
