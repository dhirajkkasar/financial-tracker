"""
Unit tests for PPF PDF parser (TDD — written first, must be RED before implementation).
"""
import pytest
from pathlib import Path
from app.importers.ppf_pdf_parser import PPFPDFParser

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestPPFPDFParser:
    @pytest.fixture
    def parser(self):
        return PPFPDFParser()

    @pytest.fixture
    def ppf_pdf_bytes(self):
        return (FIXTURES / "PPF_account_statement.pdf").read_bytes()

    def test_parse_returns_import_result(self, parser, ppf_pdf_bytes):
        result = parser.parse(ppf_pdf_bytes)
        assert result.source == "ppf_pdf"

    def test_parse_returns_two_transactions(self, parser, ppf_pdf_bytes):
        result = parser.parse(ppf_pdf_bytes)
        assert len(result.errors) == 0
        assert len(result.transactions) == 2

    def test_parse_extracts_account_number(self, parser, ppf_pdf_bytes):
        result = parser.parse(ppf_pdf_bytes)
        # Account number stripped of leading zeros: 00000032256576916 -> 32256576916
        for txn in result.transactions:
            assert txn.asset_identifier == "32256576916"

    def test_parse_first_transaction_date(self, parser, ppf_pdf_bytes):
        from datetime import date
        result = parser.parse(ppf_pdf_bytes)
        assert result.transactions[0].date == date(2018, 5, 29)

    def test_parse_second_transaction_date(self, parser, ppf_pdf_bytes):
        from datetime import date
        result = parser.parse(ppf_pdf_bytes)
        assert result.transactions[1].date == date(2018, 12, 28)

    def test_parse_first_transaction_amount(self, parser, ppf_pdf_bytes):
        result = parser.parse(ppf_pdf_bytes)
        # 5000 INR credit → CONTRIBUTION → negative (outflow convention)
        assert result.transactions[0].amount_inr == -5000.0

    def test_parse_second_transaction_amount(self, parser, ppf_pdf_bytes):
        result = parser.parse(ppf_pdf_bytes)
        # 15000 INR credit → CONTRIBUTION → negative (outflow convention)
        assert result.transactions[1].amount_inr == -15000.0

    def test_parse_transaction_type_is_contribution(self, parser, ppf_pdf_bytes):
        result = parser.parse(ppf_pdf_bytes)
        for txn in result.transactions:
            assert txn.txn_type == "CONTRIBUTION"

    def test_parse_asset_type_is_ppf(self, parser, ppf_pdf_bytes):
        result = parser.parse(ppf_pdf_bytes)
        for txn in result.transactions:
            assert txn.asset_type == "PPF"

    def test_parse_txn_id_uses_ref_no(self, parser, ppf_pdf_bytes):
        result = parser.parse(ppf_pdf_bytes)
        # First txn: Ref No. 3199410044308
        assert result.transactions[0].txn_id == "ppf_3199410044308"
        # Second txn: Ref No. IF17658260
        assert result.transactions[1].txn_id == "ppf_IF17658260"

    def test_parse_txn_ids_are_unique(self, parser, ppf_pdf_bytes):
        result = parser.parse(ppf_pdf_bytes)
        ids = [t.txn_id for t in result.transactions]
        assert len(ids) == len(set(ids))

    def test_parse_closing_balance(self, parser, ppf_pdf_bytes):
        """Parser should expose closing balance and date for Valuation creation."""
        result = parser.parse(ppf_pdf_bytes)
        assert result.closing_balance_inr == 42947.0
        assert result.closing_balance_date is not None
        from datetime import date
        assert result.closing_balance_date == date(2018, 12, 28)

    def test_parse_account_number_raw(self, parser, ppf_pdf_bytes):
        """Parser should expose the raw account number."""
        result = parser.parse(ppf_pdf_bytes)
        assert result.account_number == "32256576916"

    def test_txn_id_stable_across_reparses(self, parser, ppf_pdf_bytes):
        result1 = parser.parse(ppf_pdf_bytes)
        result2 = parser.parse(ppf_pdf_bytes)
        ids1 = [t.txn_id for t in result1.transactions]
        ids2 = [t.txn_id for t in result2.transactions]
        assert ids1 == ids2
