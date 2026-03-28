from app.services.import_service import ASSET_CLASS_MAP
from app.engine.mf_classifier import classify_mf
from app.models.asset import AssetClass


def test_nps_maps_to_debt():
    assert ASSET_CLASS_MAP["NPS"] == AssetClass.DEBT


def test_mf_classification_uses_classify_mf():
    """MF asset_class is derived from scheme_category via classify_mf, not ASSET_CLASS_MAP."""
    assert "MF" not in ASSET_CLASS_MAP
    assert classify_mf("Debt Scheme - Banking and PSU Fund") == AssetClass.DEBT
    assert classify_mf("Equity Scheme - Large Cap Fund") == AssetClass.EQUITY
    assert classify_mf(None) == AssetClass.EQUITY
