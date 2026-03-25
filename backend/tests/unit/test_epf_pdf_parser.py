"""Unit tests for EPF PDF parser — uses static fixture data, no PDF I/O."""
from tests.fixtures_data import PARSED_EPF


class TestEPFPDFParser:
    def test_parse_returns_import_result(self):
        assert PARSED_EPF.source == "epf_pdf"

    def test_parse_extracts_member_id(self):
        assert PARSED_EPF.member_id == "PYKRP00192140000152747"

    def test_parse_extracts_establishment_name(self):
        assert PARSED_EPF.establishment_name == "IBM INDIA PVT LTD"

    def test_parse_extracts_print_date(self):
        from datetime import date
        assert PARSED_EPF.print_date == date(2018, 11, 27)

    def test_parse_has_no_errors(self):
        assert len(PARSED_EPF.errors) == 0

    def test_parse_transactions_not_empty(self):
        assert len(PARSED_EPF.transactions) > 0

    def test_parse_epf_transactions_have_member_id_as_identifier(self):
        epf_txns = [t for t in PARSED_EPF.transactions
                    if t.asset_identifier == "PYKRP00192140000152747"]
        assert len(epf_txns) > 0

    def test_parse_eps_transactions_have_eps_identifier(self):
        eps_txns = [t for t in PARSED_EPF.transactions
                    if t.asset_identifier == "PYKRP00192140000152747_EPS"]
        assert len(eps_txns) > 0

    def test_parse_epf_asset_type(self):
        for txn in PARSED_EPF.transactions:
            assert txn.asset_type == "EPF"

    def test_parse_contribution_types(self):
        contribution_txns = [t for t in PARSED_EPF.transactions if t.txn_type == "CONTRIBUTION"]
        assert len(contribution_txns) > 0

    def test_parse_interest_transactions(self):
        interest_txns = [t for t in PARSED_EPF.transactions if t.txn_type == "INTEREST"]
        assert len(interest_txns) > 0

    def test_parse_transfer_transaction(self):
        transfer_txns = [t for t in PARSED_EPF.transactions if t.txn_type == "TRANSFER"]
        assert len(transfer_txns) >= 1

    def test_parse_employee_share_notes(self):
        emp_txns = [t for t in PARSED_EPF.transactions
                    if t.txn_type == "CONTRIBUTION" and t.notes == "Employee Share"
                    and t.asset_identifier == "PYKRP00192140000152747"]
        assert len(emp_txns) > 0

    def test_parse_employer_share_notes(self):
        er_txns = [t for t in PARSED_EPF.transactions
                   if t.txn_type == "CONTRIBUTION" and t.notes == "Employer Share"
                   and t.asset_identifier == "PYKRP00192140000152747"]
        assert len(er_txns) > 0

    def test_parse_pension_contribution_notes(self):
        eps_txns = [t for t in PARSED_EPF.transactions
                    if t.txn_type == "CONTRIBUTION" and t.notes == "Pension Contribution"
                    and t.asset_identifier == "PYKRP00192140000152747_EPS"]
        assert len(eps_txns) > 0

    def test_parse_contribution_amounts_are_negative(self):
        contribution_txns = [t for t in PARSED_EPF.transactions if t.txn_type == "CONTRIBUTION"]
        for txn in contribution_txns:
            assert txn.amount_inr < 0

    def test_parse_interest_amounts_are_positive(self):
        interest_txns = [t for t in PARSED_EPF.transactions if t.txn_type == "INTEREST"]
        for txn in interest_txns:
            assert txn.amount_inr > 0

    def test_parse_transfer_amount_is_positive(self):
        transfer_txns = [t for t in PARSED_EPF.transactions if t.txn_type == "TRANSFER"]
        for txn in transfer_txns:
            assert txn.amount_inr > 0

    def test_parse_all_txn_ids_unique(self):
        ids = [t.txn_id for t in PARSED_EPF.transactions]
        assert len(ids) == len(set(ids))

    # test_txn_id_stable_across_reparses removed: covered by tests/smoke/test_epf_smoke.py

    def test_parse_net_balance_is_zero(self):
        assert PARSED_EPF.net_balance_inr == 0.0

    def test_parse_grand_total_deposits(self):
        assert PARSED_EPF.grand_total_emp_deposit == 198371.0
        assert PARSED_EPF.grand_total_er_deposit == 140204.0

    def test_parse_eps_identifier_in_transactions(self):
        eps_txns = [t for t in PARSED_EPF.transactions
                    if t.asset_identifier == "PYKRP00192140000152747_EPS"]
        for txn in eps_txns:
            assert "IBM INDIA PVT LTD" in txn.asset_name
