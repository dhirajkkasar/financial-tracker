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
