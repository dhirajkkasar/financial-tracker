"""Unit tests for PPF CSV parser — uses an inline minimal CSV fixture."""
from datetime import date

from app.importers.ppf_csv_importer import PPFCSVImporter, _make_txn_id

# Minimal CSV mimicking the SBI PPF statement format (3 transactions)
MINI_CSV = b""",,,,,,,
Mr. Test User,State Bank of India,,,,,,
test@email.com,Branch Details,,,,,,
Date of Statement               :       25-03-2026,Branch Code                  :         13547,,,,,,
"Clear Balance                     :       12,543.00CR",Branch Email                  :         test@sbi.co.in,,,,,,
Uncleared Amount              :       0.00,Branch Phone                 :        0000000000,,,,,,
Lien                                     :       0.00,Account No                     :        32256576916,,,,,,
Interest Rate                       :       7.10 % p.a.,Product                           :        PPF Account,,,,,,
Account Open Date            :       29/03/2012,IFSC Code                      :       SBIN0013547,,,,,,
Date,Details,,,Ref No./Cheque No,Debit,Credit,Balance
31/03/2013,INTEREST CREDIT - WITHIN SBI ,,,,-,543.00,"12,543.00"
09/10/2012,CASH DEPOSIT SELF AT 13547 SUS ROAD PASHAN - CASH ,,,,-,"10,000.00","12,000.00"
29/03/2012,CASH DEPOSIT SELF AT 13547 SUS ROAD PASHAN - CASH ,,,,-,"2,000.00","2,000.00"
"""


class TestPPFCSVImporter:
    def setup_method(self):
        self.result = PPFCSVImporter().parse(MINI_CSV)

    def test_parse_returns_ppf_csv_source(self):
        assert self.result.source == "ppf_csv"

    def test_no_errors(self):
        assert self.result.errors == []

    def test_extracts_account_number(self):
        # Account number is now in asset_identifier of transactions
        assert self.result.transactions
        assert self.result.transactions[0].asset_identifier == "32256576916"

    def test_derives_bank_name_from_ifsc(self):
        # Bank name is derived and used in asset_name
        assert self.result.transactions
        assert "SBI" in self.result.transactions[0].asset_name

    def test_asset_name(self):
        assert self.result.transactions
        assert self.result.transactions[0].asset_name == "PPF - SBI"

    def test_transaction_count(self):
        assert len(self.result.transactions) == 3

    def test_interest_transaction_type(self):
        interest_txns = [t for t in self.result.transactions if t.txn_type == "INTEREST"]
        assert len(interest_txns) == 1

    def test_interest_amount_is_positive(self):
        interest = next(t for t in self.result.transactions if t.txn_type == "INTEREST")
        assert interest.amount_inr == 543.0
        assert interest.date == date(2013, 3, 31)

    def test_contribution_count(self):
        contribs = [t for t in self.result.transactions if t.txn_type == "CONTRIBUTION"]
        assert len(contribs) == 2

    def test_contribution_amounts_are_negative(self):
        for txn in self.result.transactions:
            if txn.txn_type == "CONTRIBUTION":
                assert txn.amount_inr < 0

    def test_all_transactions_have_ppf_asset_type(self):
        for txn in self.result.transactions:
            assert txn.asset_type == "PPF"

    def test_all_transactions_have_correct_identifier(self):
        for txn in self.result.transactions:
            assert txn.asset_identifier == "32256576916"

    def test_all_transactions_have_correct_asset_name(self):
        for txn in self.result.transactions:
            assert txn.asset_name == "PPF - SBI"

    def test_txn_ids_start_with_ppf_csv(self):
        for txn in self.result.transactions:
            assert txn.txn_id.startswith("ppf_csv_")

    def test_txn_ids_are_unique(self):
        ids = [t.txn_id for t in self.result.transactions]
        assert len(ids) == len(set(ids))

    def test_txn_id_is_stable(self):
        expected = _make_txn_id("32256576916", "INTEREST", date(2013, 3, 31), 54300)
        interest = next(t for t in self.result.transactions if t.txn_type == "INTEREST")
        assert interest.txn_id == expected

    def test_contribution_txn_id_stable(self):
        expected = _make_txn_id("32256576916", "CONTRIBUTION", date(2012, 3, 29), 200000)
        march_txn = next(
            t for t in self.result.transactions
            if t.txn_type == "CONTRIBUTION" and t.date == date(2012, 3, 29)
        )
        assert march_txn.txn_id == expected


class TestPPFCSVImporterErrors:
    def test_missing_account_number_returns_error(self):
        csv = b"Date,Details,,,Ref,Debit,Credit,Balance\n01/01/2024,Test,,,,-,1000.00,1000.00\n"
        result = PPFCSVImporter().parse(csv)
        assert any("account number" in e.lower() for e in result.errors)

    def test_missing_transaction_table_returns_error(self):
        csv = b"Account No  :  32256576916,,,,,,\n"
        result = PPFCSVImporter().parse(csv)
        assert any("transaction table" in e.lower() for e in result.errors)

    def test_no_transactions_returns_error(self):
        csv = (
            b"Account No  :  32256576916,,,,,,\n"
            b"IFSC Code  :  SBIN0013547,,,,,,\n"
            b"Date,Details,,,Ref No./Cheque No,Debit,Credit,Balance\n"
        )
        result = PPFCSVImporter().parse(csv)
        assert any("no transactions" in e.lower() for e in result.errors)
