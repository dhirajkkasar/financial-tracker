"""Unit tests for PPF PDF parser — uses static fixture data, no PDF I/O."""
from datetime import date
from tests.fixtures_data import PARSED_PPF


class TestPPFPDFParser:
    def test_parse_returns_import_result(self):
        assert PARSED_PPF.source == "ppf_pdf"

    def test_parse_returns_two_transactions(self):
        assert len(PARSED_PPF.errors) == 0
        assert len(PARSED_PPF.transactions) == 2

    def test_parse_extracts_account_number(self):
        for txn in PARSED_PPF.transactions:
            assert txn.asset_identifier == "32256576916"

    def test_parse_first_transaction_date(self):
        assert PARSED_PPF.transactions[0].date == date(2018, 5, 29)

    def test_parse_second_transaction_date(self):
        assert PARSED_PPF.transactions[1].date == date(2018, 12, 28)

    def test_parse_first_transaction_amount(self):
        assert PARSED_PPF.transactions[0].amount_inr == -5000.0

    def test_parse_second_transaction_amount(self):
        assert PARSED_PPF.transactions[1].amount_inr == -15000.0

    def test_parse_transaction_type_is_contribution(self):
        for txn in PARSED_PPF.transactions:
            assert txn.txn_type == "CONTRIBUTION"

    def test_parse_asset_type_is_ppf(self):
        for txn in PARSED_PPF.transactions:
            assert txn.asset_type == "PPF"

    def test_parse_txn_id_uses_ref_no(self):
        assert PARSED_PPF.transactions[0].txn_id == "ppf_3199410044308"
        assert PARSED_PPF.transactions[1].txn_id == "ppf_IF17658260"

    def test_parse_txn_ids_are_unique(self):
        ids = [t.txn_id for t in PARSED_PPF.transactions]
        assert len(ids) == len(set(ids))

    def test_parse_closing_balance(self):
        assert PARSED_PPF.closing_balance_inr == 42947.0
        assert PARSED_PPF.closing_balance_date == date(2018, 12, 28)

    def test_parse_account_number_raw(self):
        assert PARSED_PPF.account_number == "32256576916"

    # test_txn_id_stable_across_reparses removed: covered by tests/smoke/test_ppf_smoke.py
