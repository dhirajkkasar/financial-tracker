from datetime import date


def make_asset(**overrides):
    return {"name": "Test Asset", "asset_type": "STOCK_IN",
            "asset_class": "EQUITY", "identifier": "RELIANCE", **overrides}


def make_transaction(**overrides):
    return {"type": "BUY", "date": "2023-01-01",
            "units": 10.0, "price_per_unit": 2500.0,
            "amount_inr": -25000.0, "charges_inr": 0.0, **overrides}


def make_cashflow(date_, amount):
    return (date_, amount)
