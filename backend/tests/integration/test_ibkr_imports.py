"""IBKR Flex Trades CSV — API integration: preview/commit lands in STOCK_US (US Stocks page)."""
import json


HEADER = ("ClientAccountID,CurrencyPrimary,FXRateToBase,AssetClass,SubCategory,"
          "Symbol,CUSIP,ISIN,TradeID,DateTime,TransactionType,Quantity,"
          "TradePrice,Proceeds,Taxes,FifoPnlRealized,IBCommission,IBCommissionCurrency,Buy/Sell")
ROW_BUY = ('U25310034,USD,1,STK,COMMON,AAPL,037833100,US0378331005,9557432554,'
           '"20260522;115526",ExchTrade,5,310,-1550,0,0,-0.34477225,USD,BUY')
ROW_SELL = ('U25310034,USD,1,STK,COMMON,AAPL,037833100,US0378331005,9999999999,'
            '"20260820;101500",ExchTrade,-5,320,1600,0,0,-0.35,USD,SELL')

RATES = {"2026-05": 86.0, "2026-08": 87.5}


def _csv(*rows: str) -> bytes:
    return ("\n".join([HEADER, *rows]) + "\n").encode()


def test_ibkr_endpoint_preview_and_commit_as_stock_us(client, db):
    from app.models.asset import Asset

    csv_bytes = _csv(ROW_BUY)
    resp = client.post(
        "/import/preview-file?source=ibkr&format=csv",
        data={"user_inputs": json.dumps(RATES)},
        files={"file": ("fintrack_us_stocks.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["new_count"] == 1

    committed = client.post(f"/import/commit-file/{body['preview_id']}").json()
    assert committed["inserted"] == 1

    asset = db.query(Asset).filter(Asset.identifier == "AAPL").first()
    assert asset is not None
    assert asset.asset_type.value == "STOCK_US"  # US Stocks page filters on this
    assert asset.currency == "USD"


def test_ibkr_endpoint_missing_rate_returns_422(client):
    csv_bytes = _csv(ROW_BUY, ROW_SELL)
    resp = client.post(
        "/import/preview-file?source=ibkr&format=csv",
        data={"user_inputs": json.dumps({"2026-05": 86.0})},  # missing 2026-08
        files={"file": ("fintrack_us_stocks.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 422
    assert "2026-08" in resp.text
