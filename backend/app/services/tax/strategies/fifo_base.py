# backend/app/services/tax/strategies/fifo_base.py
from __future__ import annotations

from datetime import date
from typing import ClassVar

from app.engine.lot_engine import match_lots_fifo
from app.repositories.unit_of_work import UnitOfWork
from app.services.returns.strategies.market_based import LOT_TYPES, SELL_TYPES, _Lot, _Sell
from app.services.tax.strategies.base import AssetTaxGainsResult, TaxGainsStrategy


class FifoTaxGainsStrategy(TaxGainsStrategy):
    """
    Base for all FIFO lot-matched assets.

    Subclasses declare ClassVars:
        stcg_days: int             — holding threshold in days
        stcg_rate_pct: float|None  — None means slab rate
        ltcg_rate_pct: float|None  — None means slab rate
        ltcg_exempt_eligible: bool — True for STOCK_IN and equity MF (Section 112A)
        ltcg_slab: bool            — True if LTCG is slab-rated (Debt MF)
    """

    stcg_days: ClassVar[int]
    stcg_rate_pct: ClassVar[float | None] = None
    ltcg_rate_pct: ClassVar[float | None] = None
    ltcg_exempt_eligible: ClassVar[bool] = False
    ltcg_slab: ClassVar[bool] = False

    # ── Lot building (duplicated from MarketBasedStrategy — refactored in Task 13) ──

    def _build_lots_sells(self, txns) -> tuple[list[_Lot], list[_Sell]]:
        lots: list[_Lot] = []
        sells: list[_Sell] = []
        for t in sorted(txns, key=lambda x: x.date):
            ttype = t.type.value if hasattr(t.type, "value") else str(t.type)
            if ttype in LOT_TYPES and t.units:
                is_bonus = ttype == "BONUS"
                price_pu = 0.0 if is_bonus else (
                    abs(t.amount_inr / 100.0) / t.units if t.units else 0.0
                )
                lots.append(_Lot(
                    lot_id=t.lot_id or str(t.id),
                    buy_date=t.date,
                    units=t.units,
                    buy_price_per_unit=price_pu,
                    buy_amount_inr=0.0 if is_bonus else abs(t.amount_inr / 100.0),
                ))
            elif ttype in SELL_TYPES and t.units:
                sells.append(_Sell(
                    date=t.date,
                    units=t.units,
                    amount_inr=abs(t.amount_inr / 100.0),
                ))
        return lots, sells

    # ── FY gain extraction ──────────────────────────────────────────────────────

    def _fy_gains(
        self, matched: list[dict], fy_start: date, fy_end: date
    ) -> tuple[float, float]:
        """Filter matches by sell date in FY, return (st_gain, lt_gain)."""
        st, lt = 0.0, 0.0
        for m in matched:
            sell_date = m["sell_date"]
            if isinstance(sell_date, str):
                sell_date = date.fromisoformat(sell_date)
            if not (fy_start <= sell_date <= fy_end):
                continue
            gain = m["realised_gain_inr"]
            # is_short_term already set by match_lots_fifo using self.stcg_days
            if m["is_short_term"]:
                st += gain
            else:
                lt += gain
        return st, lt

    # ── Tax estimation ──────────────────────────────────────────────────────────

    def _tax(self, gain: float, rate_pct: float | None, slab_rate_pct: float) -> float:
        if gain <= 0:
            return 0.0
        rate = rate_pct if rate_pct is not None else slab_rate_pct
        return gain * rate / 100.0

    # ── Public entry point ──────────────────────────────────────────────────────

    def compute(
        self,
        asset,
        uow: UnitOfWork,
        fy_start: date,
        fy_end: date,
        slab_rate_pct: float,
    ) -> AssetTaxGainsResult:
        txns = uow.transactions.list_by_asset(asset.id)
        lots, sells = self._build_lots_sells(txns)

        st_gain, lt_gain = 0.0, 0.0
        if lots and sells:
            matched = match_lots_fifo(lots, sells, stcg_days=self.stcg_days)
            st_gain, lt_gain = self._fy_gains(matched, fy_start, fy_end)

        has_slab = (self.stcg_rate_pct is None and st_gain != 0) or (
            self.ltcg_rate_pct is None and lt_gain != 0
        )

        return AssetTaxGainsResult(
            asset_id=asset.id,
            asset_name=asset.name,
            asset_type=asset.asset_type.value,
            asset_class=asset.asset_class.value,
            st_gain=st_gain,
            lt_gain=lt_gain,
            st_tax_estimate=self._tax(st_gain, self.stcg_rate_pct, slab_rate_pct),
            lt_tax_estimate=self._tax(lt_gain, self.ltcg_rate_pct, slab_rate_pct),
            ltcg_exemption_used=0.0,
            has_slab=has_slab,
            ltcg_exempt_eligible=self.ltcg_exempt_eligible,
            ltcg_slab=self.ltcg_slab,
        )
