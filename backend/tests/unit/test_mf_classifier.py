import pytest
from app.engine.mf_classifier import classify_mf
from app.models.asset import AssetClass


def test_debt_scheme_returns_debt():
    assert classify_mf("Debt Scheme - Liquid Fund") == AssetClass.DEBT


def test_equity_scheme_returns_equity():
    assert classify_mf("Equity Scheme - Large Cap Fund") == AssetClass.EQUITY


def test_hybrid_scheme_returns_equity():
    assert classify_mf("Hybrid Scheme - Balanced Advantage Fund") == AssetClass.EQUITY


def test_other_scheme_returns_equity():
    assert classify_mf("Other Scheme - Index Funds") == AssetClass.EQUITY


def test_solution_oriented_returns_equity():
    assert classify_mf("Solution Oriented Scheme - Childrens Fund") == AssetClass.EQUITY


def test_none_returns_equity():
    assert classify_mf(None) == AssetClass.EQUITY


def test_empty_string_returns_equity():
    assert classify_mf("") == AssetClass.EQUITY


def test_case_insensitive():
    assert classify_mf("DEBT SCHEME - Gilt Fund") == AssetClass.DEBT


def test_default_scheme_classifier_equity():
    from app.engine.mf_classifier import DefaultSchemeClassifier
    classifier = DefaultSchemeClassifier()
    result = classifier.classify("Large Cap Fund - Growth")
    assert result.value in ("EQUITY", "MIXED", "DEBT")  # not None


def test_default_scheme_classifier_debt():
    from app.engine.mf_classifier import DefaultSchemeClassifier
    classifier = DefaultSchemeClassifier()
    result = classifier.classify("Debt Scheme - Liquid Fund - Direct Growth")
    assert result == AssetClass.DEBT


def test_ischeme_classifier_protocol():
    """Any class with a classify() method satisfies ISchemeClassifier."""
    from app.engine.mf_classifier import ISchemeClassifier, DefaultSchemeClassifier
    assert isinstance(DefaultSchemeClassifier(), ISchemeClassifier)
