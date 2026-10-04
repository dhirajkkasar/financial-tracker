import csv
import io
from datetime import date

import pytest

from app.importers.ibkr_csv_importer import IBKRTradesImporter


RATES_JSON = '{"2026-04": 85.0, "2026-05": 86.0, "2026-08": 87.5}'

HEADER = ("ClientAccountID,CurrencyPrimary,FXRateToBase,AssetClass,SubCategory,"
          "Symbol,CUSIP,ISIN,TradeID,DateTime,TransactionType,Quantity,"
          "TradePrice,Proceeds,Taxes,FifoPnlRealized,IBCommission,IBCommissionCurrency,Buy/Sell")

ROW_BUY = ('U25310034,USD,1,STK,COMMON,AAPL,037833100,US0378331005,9557432554,'
           '"20260522;115526",ExchTrade,5,310,-1550,0,0,-0.34477225,USD,BUY')
ROW_BUY_FRAC = ('U25310034,USD,1,STK,COMMON,NVDA,67066G104,US67066G1040,9349840865,'
                '"20260420;104435",ExchTrade,0.6226,199.16,-123.997016,0,0,-1,USD,BUY')
ROW_SELL = ('U25310034,USD,1,STK,COMMON,AAPL,037833100,US0378331005,9999999999,'
            '"20260820;101500",ExchTrade,-5,320,1600,0,0,-0.35,USD,SELL')
ROW_ETF = ('U25310034,USD,1,STK,ETF,VOO,922908363,US9229083632,9558404981,'
           '"20260522;132000",ExchTrade,5,686.5,-3432.5,0,0,-0.34327225,USD,BUY')


def _csv(*rows: str) -> bytes:
    return ("\n".join([HEADER, *rows]) + "\n").encode()


class TestIBKRParse:
    def test_buy_fields(self):
        result = IBKRTradesImporter(user_inputs=RATES_JSON).parse(_csv(ROW_BUY))
        assert result.errors == []
        txn = result.transactions[0]
        assert txn.asset_name == "AAPL"
        assert txn.asset_identifier == "AAPL"
        assert txn.asset_type == "STOCK_US"
        assert txn.txn_type == "BUY"
        assert txn.date == date(2026, 5, 22)
        assert txn.units == pytest.approx(5.0)
        assert txn.price_per_unit == pytest.approx(310.0)
        assert txn.forex_rate == pytest.approx(86.0)
        # (|1550| + 0.34477225) * 86
        assert txn.amount_inr == pytest.approx(-(1550 + 0.34477225) * 86.0, rel=1e-6)
        assert txn.txn_id == "ibkr_9557432554"

    def test_sell_is_inflow(self):
        result = IBKRTradesImporter(user_inputs=RATES_JSON).parse(_csv(ROW_SELL))
        txn = result.transactions[0]
        assert txn.txn_type == "SELL"
        assert txn.units == pytest.approx(5.0)
        assert txn.amount_inr == pytest.approx((1600 - 0.35) * 87.5, rel=1e-6)

    def test_fractional_and_etf_map_to_stock_us(self):
        result = IBKRTradesImporter(user_inputs=RATES_JSON).parse(_csv(ROW_BUY_FRAC, ROW_ETF))
        assert [t.asset_type for t in result.transactions] == ["STOCK_US", "STOCK_US"]
        assert result.transactions[0].units == pytest.approx(0.6226)
        assert result.transactions[1].asset_name == "VOO"

    def test_txn_id_stable_native_tradeid(self):
        imp = IBKRTradesImporter(user_inputs=RATES_JSON)
        assert imp.parse(_csv(ROW_BUY)).transactions[0].txn_id == "ibkr_9557432554"

    def test_extract_required_months(self):
        months = IBKRTradesImporter.extract_required_month_years(_csv(ROW_BUY, ROW_BUY_FRAC, ROW_SELL))
        assert months == ["2026-04", "2026-05", "2026-08"]

    def test_missing_rate_is_row_error(self):
        result = IBKRTradesImporter(user_inputs='{"2026-05": 86.0}').parse(_csv(ROW_BUY, ROW_BUY_FRAC))
        assert len(result.transactions) == 1
        assert any("2026-04" in e for e in result.errors)

    def test_non_us_currency_rejected(self):
        row = ROW_BUY.replace(",USD,1,", ",EUR,1,", 1)
        result = IBKRTradesImporter(user_inputs=RATES_JSON).parse(_csv(row))
        assert result.transactions == []
        assert any("currency" in e.lower() for e in result.errors)

    def test_non_trade_rows_skipped_with_warning(self):
        div = ROW_BUY.replace("ExchTrade", "Dividends").replace("9557432554", "111")
        result = IBKRTradesImporter(user_inputs=RATES_JSON).parse(_csv(div))
        assert result.transactions == []
        assert any("skip" in w.lower() for w in result.warnings)


class TestIBKRValidate:
    def test_validate_blocks_without_rates(self):
        result = IBKRTradesImporter().parse(_csv(ROW_BUY))
        vr = IBKRTradesImporter().validate(result)
        assert vr.is_valid is False
        assert "2026-05" in vr.errors[0]

    def test_validate_passes_with_complete_rates(self):
        result = IBKRTradesImporter().parse(_csv(ROW_BUY))
        vr = IBKRTradesImporter(user_inputs='{"2026-05": 86.0}').validate(result)
        assert vr.is_valid is True
