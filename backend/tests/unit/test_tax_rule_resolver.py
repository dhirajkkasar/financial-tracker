import pytest
from datetime import date
from pathlib import Path

from app.engine.tax_engine import TaxRuleResolver, ResolvedTaxRule


@pytest.fixture
def resolver(tmp_path):
    """Create a resolver with a test YAML config."""
    config = tmp_path / "2025-26.yaml"
    config.write_text("""
STOCK_IN:
  stcg_rate_pct: 20.0
  ltcg_rate_pct: 12.5
  stcg_days: 365
  ltcg_exemption_inr: 125000
  ltcg_exempt_eligible: true

STOCK_US:
  stcg_rate_pct: null
  ltcg_rate_pct: 12.5
  stcg_days: 730

GOLD:
  stcg_rate_pct: null
  ltcg_rate_pct: 12.5
  stcg_days: 1095

REAL_ESTATE:
  stcg_rate_pct: null
  ltcg_rate_pct: 12.5
  stcg_days: 730

MF:
  stcg_rate_pct: 20.0
  ltcg_rate_pct: 12.5
  stcg_days: 365
  ltcg_exemption_inr: 125000
  ltcg_exempt_eligible: true
  overrides:
    - match:
        bought_before: "2020-01-01"
      stcg_rate_pct: 15.0

  DEBT:
    stcg_rate_pct: null
    ltcg_rate_pct: 12.5
    stcg_days: 730
    ltcg_exemption_inr: 0
    ltcg_exempt_eligible: false
    overrides:
      - match:
          bought_on_or_after: "2023-04-01"
        ltcg_rate_pct: null

  EQUITY:
    overrides:
      - match:
          isins: ["INF209KB1YA0"]
        stcg_days: 730
        stcg_rate_pct: null
        ltcg_exemption_inr: 0
        ltcg_exempt_eligible: false
      - match:
          isins: ["INF209KB1YA0"]
          bought_on_or_after: "2023-04-01"
        ltcg_rate_pct: null
""")
    return TaxRuleResolver(tmp_path)


def test_simple_asset_type_defaults(resolver):
    rule = resolver.resolve("2025-26", "STOCK_IN")
    assert rule.stcg_rate_pct == 20.0
    assert rule.ltcg_rate_pct == 12.5
    assert rule.stcg_days == 365
    assert rule.ltcg_exemption_inr == 125000
    assert rule.ltcg_exempt_eligible is True


def test_defaults_for_optional_keys(resolver):
    """STOCK_US has no ltcg_exemption_inr or ltcg_exempt_eligible — should get defaults."""
    rule = resolver.resolve("2025-26", "STOCK_US")
    assert rule.stcg_rate_pct is None
    assert rule.ltcg_rate_pct == 12.5
    assert rule.stcg_days == 730
    assert rule.ltcg_exemption_inr == 0.0
    assert rule.ltcg_exempt_eligible is False


def test_asset_class_overrides_parent(resolver):
    """MF DEBT overrides stcg_rate_pct to None (slab) from MF default of 20.0."""
    rule = resolver.resolve("2025-26", "MF", asset_class="DEBT")
    assert rule.stcg_rate_pct is None
    assert rule.ltcg_rate_pct == 12.5
    assert rule.stcg_days == 730
    assert rule.ltcg_exemption_inr == 0
    assert rule.ltcg_exempt_eligible is False


def test_asset_class_inherits_unspecified_keys(resolver):
    """MF EQUITY has no direct keys — inherits all from MF default."""
    rule = resolver.resolve("2025-26", "MF", asset_class="EQUITY")
    assert rule.stcg_rate_pct == 20.0
    assert rule.ltcg_rate_pct == 12.5
    assert rule.stcg_days == 365
    assert rule.ltcg_exemption_inr == 125000
    assert rule.ltcg_exempt_eligible is True


def test_asset_type_level_override_by_date(resolver):
    """MF default has override: bought_before 2020-01-01 → stcg_rate_pct 15.0."""
    rule = resolver.resolve("2025-26", "MF", buy_date=date(2019, 6, 1))
    assert rule.stcg_rate_pct == 15.0
    # bought after cutoff — no override
    rule2 = resolver.resolve("2025-26", "MF", buy_date=date(2021, 1, 1))
    assert rule2.stcg_rate_pct == 20.0


def test_asset_class_epoch_override(resolver):
    """MF DEBT post-2023: ltcg_rate_pct becomes None (slab)."""
    rule = resolver.resolve("2025-26", "MF", asset_class="DEBT",
                            buy_date=date(2023, 6, 1))
    assert rule.ltcg_rate_pct is None
    assert rule.stcg_rate_pct is None


def test_debt_mf_pre2023_keeps_ltcg(resolver):
    """MF DEBT pre-2023: ltcg_rate_pct stays 12.5."""
    rule = resolver.resolve("2025-26", "MF", asset_class="DEBT",
                            buy_date=date(2022, 1, 1))
    assert rule.ltcg_rate_pct == 12.5


def test_isin_override(resolver):
    """MF EQUITY with specific ISIN gets foreign-equity-like rules."""
    rule = resolver.resolve("2025-26", "MF", asset_class="EQUITY",
                            isin="INF209KB1YA0")
    assert rule.stcg_days == 730
    assert rule.stcg_rate_pct is None
    assert rule.ltcg_exemption_inr == 0
    assert rule.ltcg_exempt_eligible is False
    # ltcg_rate_pct still 12.5 (no epoch match without buy_date)
    assert rule.ltcg_rate_pct == 12.5


def test_isin_plus_epoch_override(resolver):
    """MF EQUITY + specific ISIN + post-2023: ltcg_rate_pct becomes None."""
    rule = resolver.resolve("2025-26", "MF", asset_class="EQUITY",
                            isin="INF209KB1YA0", buy_date=date(2024, 1, 1))
    assert rule.ltcg_rate_pct is None
    assert rule.stcg_days == 730


def test_isin_no_match_gets_default(resolver):
    """MF EQUITY with non-matching ISIN gets default MF EQUITY rules."""
    rule = resolver.resolve("2025-26", "MF", asset_class="EQUITY",
                            isin="INF999ZZ9ZZ9")
    assert rule.stcg_rate_pct == 20.0
    assert rule.stcg_days == 365


def test_missing_fy_raises(resolver):
    with pytest.raises(ValueError, match="No tax rate config"):
        resolver.resolve("2099-00", "STOCK_IN")


def test_missing_asset_type_raises(resolver):
    with pytest.raises(KeyError):
        resolver.resolve("2025-26", "UNKNOWN_TYPE")


def test_resolved_tax_rule_is_frozen():
    rule = ResolvedTaxRule(
        stcg_rate_pct=20.0, ltcg_rate_pct=12.5, stcg_days=365,
        ltcg_exemption_inr=125000, ltcg_exempt_eligible=True,
    )
    with pytest.raises(AttributeError):
        rule.stcg_rate_pct = 99.0
