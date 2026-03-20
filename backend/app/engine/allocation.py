"""
Allocation engine — pure functions, no DB access.

compute_allocation: groups asset current values by asset_class, returns % breakdown.
find_top_gainers: sorts assets by absolute_return_pct, returns top N gainers/losers.
"""
from collections import defaultdict


def compute_allocation(entries: list[dict]) -> dict:
    """
    Group current values by asset_class and compute percentage of total.

    Args:
        entries: list of {"asset_class": str, "current_value": float}

    Returns:
        {
          "total_value": float,
          "allocations": [{"asset_class": str, "value_inr": float, "pct_of_total": float}, ...]
          # sorted by value_inr desc, zero-value classes excluded
        }
    """
    grouped: dict[str, float] = defaultdict(float)
    for entry in entries:
        grouped[entry["asset_class"]] += entry["current_value"]

    total = sum(grouped.values())

    if total <= 0:
        return {"total_value": 0.0, "allocations": []}

    allocations = [
        {
            "asset_class": cls,
            "value_inr": value,
            "pct_of_total": round(value / total * 100, 4),
        }
        for cls, value in grouped.items()
        if value > 0
    ]
    allocations.sort(key=lambda x: x["value_inr"], reverse=True)

    return {"total_value": total, "allocations": allocations}


def find_top_gainers(
    entries: list[dict],
    n: int = 5,
    gainers: bool = True,
) -> list[dict]:
    """
    Return the top N assets sorted by absolute_return_pct.

    Args:
        entries: list of dicts that include "absolute_return_pct" (float | None)
        n:       how many to return
        gainers: True → sort descending (best gains first)
                 False → sort ascending (worst losses first)

    Returns:
        Filtered and sorted list of up to n entries.
    """
    valid = [e for e in entries if e.get("absolute_return_pct") is not None]
    valid.sort(key=lambda e: e["absolute_return_pct"], reverse=gainers)
    return valid[:n]
