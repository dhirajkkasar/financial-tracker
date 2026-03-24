from app.services.import_service import ASSET_CLASS_MAP
from app.models.asset import AssetClass


def test_nps_maps_to_debt():
    assert ASSET_CLASS_MAP["NPS"] == AssetClass.DEBT


def test_mf_maps_to_mixed():
    """MF stays MIXED in the map; classification happens via price feed."""
    assert ASSET_CLASS_MAP["MF"] == AssetClass.MIXED
