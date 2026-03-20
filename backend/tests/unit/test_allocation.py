"""Unit tests for allocation engine (Phase 3.2). TDD: RED first."""
import pytest
from app.engine.allocation import compute_allocation, find_top_gainers


# ---------------------------------------------------------------------------
# compute_allocation
# ---------------------------------------------------------------------------

class TestComputeAllocation:
    def test_empty_input_returns_empty(self):
        result = compute_allocation([])
        assert result["allocations"] == []
        assert result["total_value"] == 0.0

    def test_single_class_100_pct(self):
        entries = [{"asset_class": "EQUITY", "current_value": 100_000.0}]
        result = compute_allocation(entries)
        assert len(result["allocations"]) == 1
        alloc = result["allocations"][0]
        assert alloc["asset_class"] == "EQUITY"
        assert alloc["value_inr"] == pytest.approx(100_000.0)
        assert alloc["pct_of_total"] == pytest.approx(100.0)

    def test_two_classes_split_evenly(self):
        entries = [
            {"asset_class": "EQUITY", "current_value": 50_000.0},
            {"asset_class": "DEBT", "current_value": 50_000.0},
        ]
        result = compute_allocation(entries)
        assert result["total_value"] == pytest.approx(100_000.0)
        pcts = {a["asset_class"]: a["pct_of_total"] for a in result["allocations"]}
        assert pcts["EQUITY"] == pytest.approx(50.0)
        assert pcts["DEBT"] == pytest.approx(50.0)

    def test_groups_multiple_assets_same_class(self):
        entries = [
            {"asset_class": "EQUITY", "current_value": 30_000.0},
            {"asset_class": "EQUITY", "current_value": 70_000.0},
            {"asset_class": "DEBT", "current_value": 100_000.0},
        ]
        result = compute_allocation(entries)
        values = {a["asset_class"]: a["value_inr"] for a in result["allocations"]}
        assert values["EQUITY"] == pytest.approx(100_000.0)
        assert values["DEBT"] == pytest.approx(100_000.0)

    def test_pct_sum_equals_100(self):
        entries = [
            {"asset_class": "EQUITY", "current_value": 60_000.0},
            {"asset_class": "DEBT", "current_value": 30_000.0},
            {"asset_class": "GOLD", "current_value": 10_000.0},
        ]
        result = compute_allocation(entries)
        total_pct = sum(a["pct_of_total"] for a in result["allocations"])
        assert total_pct == pytest.approx(100.0)

    def test_sorted_by_value_desc(self):
        entries = [
            {"asset_class": "GOLD", "current_value": 10_000.0},
            {"asset_class": "EQUITY", "current_value": 90_000.0},
        ]
        result = compute_allocation(entries)
        classes = [a["asset_class"] for a in result["allocations"]]
        assert classes[0] == "EQUITY"

    def test_zero_value_assets_excluded(self):
        entries = [
            {"asset_class": "EQUITY", "current_value": 100_000.0},
            {"asset_class": "REAL_ESTATE", "current_value": 0.0},
        ]
        result = compute_allocation(entries)
        classes = [a["asset_class"] for a in result["allocations"]]
        assert "REAL_ESTATE" not in classes


# ---------------------------------------------------------------------------
# find_top_gainers
# ---------------------------------------------------------------------------

class TestFindTopGainers:
    def _entry(self, asset_id, name, abs_return_pct):
        return {
            "asset_id": asset_id,
            "name": name,
            "asset_type": "STOCK_IN",
            "total_invested": 100_000.0,
            "current_value": 100_000.0 * (1 + abs_return_pct / 100),
            "absolute_return_pct": abs_return_pct,
            "xirr": None,
        }

    def test_returns_sorted_desc(self):
        entries = [
            self._entry(1, "A", 5.0),
            self._entry(2, "B", 20.0),
            self._entry(3, "C", 10.0),
        ]
        result = find_top_gainers(entries, n=5)
        assert result[0]["asset_id"] == 2
        assert result[1]["asset_id"] == 3
        assert result[2]["asset_id"] == 1

    def test_limits_to_n(self):
        entries = [self._entry(i, f"A{i}", float(i)) for i in range(10)]
        result = find_top_gainers(entries, n=5)
        assert len(result) == 5

    def test_excludes_null_return(self):
        entries = [
            self._entry(1, "A", 10.0),
            {**self._entry(2, "B", 0.0), "absolute_return_pct": None},
        ]
        result = find_top_gainers(entries, n=5)
        ids = [r["asset_id"] for r in result]
        assert 2 not in ids

    def test_empty_input_returns_empty(self):
        assert find_top_gainers([], n=5) == []

    def test_default_n_is_5(self):
        entries = [self._entry(i, f"A{i}", float(i)) for i in range(10)]
        assert len(find_top_gainers(entries)) == 5

    def test_losers_flag(self):
        """find_top_gainers with gainers=False returns bottom N (losers) sorted asc."""
        entries = [
            self._entry(1, "A", -15.0),
            self._entry(2, "B", 5.0),
            self._entry(3, "C", -30.0),
        ]
        result = find_top_gainers(entries, n=2, gainers=False)
        assert result[0]["asset_id"] == 3  # worst loss first
        assert result[1]["asset_id"] == 1
