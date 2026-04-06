import pytest
from datetime import date
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _make_sample_pdf_bytes() -> bytes:
    path = FIXTURES / "fidelity_sale_sample.pdf"
    if path.exists():
        return path.read_bytes()
    pytest.skip("fidelity_sale_sample.pdf fixture not available")


class TestFidelityPDFImporter:
    RATES = {"2025-03": 86.0, "2025-09": 84.5}

    def _parse(self):
        from app.importers.fidelity_pdf_importer import FidelityPDFImporter
        data = _make_sample_pdf_bytes()
        return FidelityPDFImporter(exchange_rates=self.RATES).parse(data)

    # --- Structural ---

    def test_parse_returns_one_transaction_per_sale_row(self):
        """Each PDF sale row now produces exactly 1 SELL (no synthetic BUY)."""
        result = self._parse()
        # fixture has 2 sale rows → 2 transactions
        assert len(result.transactions) == 2
        assert result.errors == []

    def test_all_transactions_are_sells(self):
        result = self._parse()
        for t in result.transactions:
            assert t.txn_type == "SELL"

    def test_no_buy_transactions_emitted(self):
        result = self._parse()
        assert all(t.txn_type != "BUY" for t in result.transactions)

    # --- Sell transaction fields ---

    def test_sell_asset_type_and_name(self):
        t = self._parse().transactions[0]
        assert t.asset_type == "STOCK_US"
        assert t.asset_name == "AMZN"
        assert t.asset_identifier == "AMZN"

    def test_sell_date(self):
        t = self._parse().transactions[0]
        assert t.date == date(2025, 3, 17)

    def test_sell_units(self):
        t = self._parse().transactions[0]
        assert t.units == pytest.approx(36.0)

    def test_sell_amount_inr_positive_inflow(self):
        # proceeds = $7,070.24, rate = 86.0
        t = self._parse().transactions[0]
        assert t.amount_inr == pytest.approx(7070.24 * 86.0, rel=1e-4)
        assert t.amount_inr > 0

    def test_sell_forex_rate(self):
        t = self._parse().transactions[0]
        assert t.forex_rate == pytest.approx(86.0)

    def test_sell_lot_id_is_none(self):
        """lot_id is None — FidelityPreCommitProcessor will assign it."""
        t = self._parse().transactions[0]
        assert t.lot_id is None

    # --- Acquisition metadata fields (NEW) ---

    def test_sell_acquisition_date_populated(self):
        t = self._parse().transactions[0]
        assert t.acquisition_date == date(2025, 3, 17)  # same date = sell-to-cover fixture

    def test_sell_acquisition_cost_inr_populated(self):
        # cost = $7,070.44, rate = 86.0 → 607,857.84 INR
        t = self._parse().transactions[0]
        assert t.acquisition_cost == pytest.approx(7070.44 * 86.0, rel=1e-4)
        assert t.acquisition_cost > 0

    def test_sell_acquisition_forex_rate_populated(self):
        t = self._parse().transactions[0]
        assert t.acquisition_forex_rate == pytest.approx(86.0)

    # --- txn_id stability ---

    def test_sell_txn_id_is_stable(self):
        """txn_id scheme unchanged: hash(ticker|date_sold|date_acquired|qty)."""
        r1 = self._parse()
        r2 = self._parse()
        assert r1.transactions[0].txn_id == r2.transactions[0].txn_id

    def test_sell_txn_id_not_empty(self):
        t = self._parse().transactions[0]
        assert t.txn_id and len(t.txn_id) > 10

    def test_extract_required_month_years(self):
        from app.importers.fidelity_pdf_importer import FidelityPDFImporter
        data = _make_sample_pdf_bytes()
        months = FidelityPDFImporter.extract_required_month_years(data)
        assert "2025-03" in months
        assert "2025-09" in months

    def test_missing_rate_adds_error(self):
        from app.importers.fidelity_pdf_importer import FidelityPDFImporter
        data = _make_sample_pdf_bytes()
        result = FidelityPDFImporter(exchange_rates={"2025-03": 86.0}).parse(data)
        # 2025-09 row should error
        assert any("2025-09" in e for e in result.errors)


class TestFidelityPDFImporterValidation:
    """Test post-parse validation of Fidelity PDF importer."""

    def _load_data(self):
        path = FIXTURES / "fidelity_sale_sample.pdf"
        if path.exists():
            return path.read_bytes()
        pytest.skip("fidelity_sale_sample.pdf fixture not available")

    def test_validate_with_valid_exchange_rates(self):
        """Validation passes when exchange_rates JSON is valid and complete."""
        from app.importers.fidelity_pdf_importer import FidelityPDFImporter
        data = self._load_data()
        result = FidelityPDFImporter().parse(data)

        # Valid exchange_rates JSON string
        user_inputs = '{"2025-03": 86.0, "2025-09": 84.5}'
        validation_result = FidelityPDFImporter().validate(result, user_inputs=user_inputs)

        assert validation_result.is_valid is True
        assert validation_result.errors == []

    def test_validate_with_invalid_json(self):
        """Validation fails when exchange_rates is not valid JSON."""
        from app.importers.fidelity_pdf_importer import FidelityPDFImporter
        data = self._load_data()
        result = FidelityPDFImporter().parse(data)

        # Invalid JSON
        user_inputs = '{invalid json}'
        validation_result = FidelityPDFImporter().validate(result, user_inputs=user_inputs)

        assert validation_result.is_valid is False
        assert len(validation_result.errors) > 0
        assert "valid JSON" in validation_result.errors[0]

    def test_validate_with_non_numeric_values(self):
        """Validation fails when exchange_rates values are not numeric."""
        from app.importers.fidelity_pdf_importer import FidelityPDFImporter
        data = self._load_data()
        result = FidelityPDFImporter().parse(data)

        # Non-numeric values
        user_inputs = '{"2025-03": "not_a_number"}'
        validation_result = FidelityPDFImporter().validate(result, user_inputs=user_inputs)

        assert validation_result.is_valid is False
        assert len(validation_result.errors) > 0
        assert "numbers" in validation_result.errors[0]

    def test_validate_with_missing_months(self):
        """Validation fails when required months are missing from exchange_rates."""
        from app.importers.fidelity_pdf_importer import FidelityPDFImporter
        data = self._load_data()
        result = FidelityPDFImporter().parse(data)

        # Missing 2025-09
        user_inputs = '{"2025-03": 86.0}'
        validation_result = FidelityPDFImporter().validate(result, user_inputs=user_inputs)

        assert validation_result.is_valid is False
        assert len(validation_result.errors) > 0
        assert "Missing exchange_rates" in validation_result.errors[0]
        assert "2025-09" in validation_result.errors[0]
        assert "2025-03" in validation_result.required_inputs.get("required_months", [])
        assert "2025-09" in validation_result.required_inputs.get("required_months", [])

    def test_validate_with_no_transactions(self):
        """Validation passes when there are no transactions and no exchange_rates."""
        from app.importers.fidelity_pdf_importer import FidelityPDFImporter
        from app.importers.base import ImportResult
        result = ImportResult(source="fidelity_sale", transactions=[])

        validation_result = FidelityPDFImporter().validate(result, user_inputs=None)

        assert validation_result.is_valid is True
        assert validation_result.errors == []

    def test_validate_with_no_user_inputs_but_transactions(self):
        """Validation fails when there are transactions but no exchange_rates provided."""
        from app.importers.fidelity_pdf_importer import FidelityPDFImporter
        data = self._load_data()
        result = FidelityPDFImporter().parse(data)

        # No user_inputs provided
        validation_result = FidelityPDFImporter().validate(result, user_inputs=None)

        assert validation_result.is_valid is False
        assert len(validation_result.errors) > 0
        assert "exchange_rates is required" in validation_result.errors[0]
