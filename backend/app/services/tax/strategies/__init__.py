# Import all strategy modules to trigger @register_tax_strategy decorators.
# Order does not matter.
from app.services.tax.strategies import (  # noqa: F401
    indian_equity,
    foreign_equity,
    gold,
    debt_mf,
    accrued_interest,
    real_estate,
)
