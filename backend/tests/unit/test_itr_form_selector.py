"""ITR-1 vs ITR-2 selection (spec section 6)."""
from app.engine.itr.form_selector import FormSelectionInput, select_form


def _base(**kw):
    base = dict(residential_status="RES", total_income=900_000.0)
    base.update(kw)
    return FormSelectionInput(**base)


def test_plain_salary_is_itr1():
    sel = select_form(_base())
    assert sel.form == "ITR1"


def test_reasons_explain_itr2():
    sel = select_form(_base(has_foreign_assets=True))
    assert sel.form == "ITR2"
    assert sel.reasons


def test_income_above_50L_is_itr2():
    assert select_form(_base(total_income=5_100_000.0)).form == "ITR2"


def test_foreign_assets_or_income_force_itr2():
    assert select_form(_base(has_foreign_assets=True)).form == "ITR2"
    assert select_form(_base(has_foreign_income=True)).form == "ITR2"


def test_112a_above_exemption_force_itr2():
    assert select_form(_base(ltcg_112a=125_000.0)).form == "ITR1"   # exactly at limit
    assert select_form(_base(ltcg_112a=125_001.0)).form == "ITR2"


def test_equity_stcg_111a_forces_itr2():
    assert select_form(_base(stcg_111a=1.0)).form == "ITR2"


def test_other_capital_gains_force_itr2():
    assert select_form(_base(other_capital_gains=1.0)).form == "ITR2"


def test_carry_forward_losses_force_itr2():
    assert select_form(_base(has_carry_forward_losses=True)).form == "ITR2"


def test_more_than_one_house_property_forces_itr2():
    assert select_form(_base(house_property_count=1)).form == "ITR1"
    assert select_form(_base(house_property_count=2)).form == "ITR2"


def test_non_resident_forces_itr2():
    for status in ("NRI", "NOR"):
        assert select_form(_base(residential_status=status)).form == "ITR2"


def test_unlisted_shares_and_crypto_force_itr2():
    assert select_form(_base(has_unlisted_shares=True)).form == "ITR2"
    assert select_form(_base(has_crypto=True)).form == "ITR2"


def test_huf_is_not_eligible_for_itr1():
    assert select_form(_base(is_huf=True)).form == "ITR2"


def test_selection_is_reported_for_the_leafy_case():
    # The real user: foreign stocks + gains -> ITR-2 with multiple reasons.
    sel = select_form(_base(has_foreign_assets=True, ltcg_112a=300_000.0, stcg_111a=50_000.0))
    assert sel.form == "ITR2"
    assert len(sel.reasons) >= 2
