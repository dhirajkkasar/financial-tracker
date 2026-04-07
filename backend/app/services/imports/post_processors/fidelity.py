"""
FidelityPreCommitProcessor — resolves lot_id on SELL transactions from Fidelity PDF imports.

Runs inside ImportOrchestrator.commit() before the transaction loop.
For each SELL with acquisition_date:
  - Queries DB for BUY/VEST transactions on that date for the asset (FIFO among same-date lots)
  - Splits the SELL into N partial-SELL transactions, each pinned to a specific lot_id
  - If no lots found and acquisition_date == date_sold: sell-to-cover → BUY+SELL pair
  - If no lots found and dates differ: orphaned sale → synthetic BUY + SELL pair
"""
import hashlib
import logging
import uuid
from dataclasses import replace
from datetime import date
from typing import ClassVar, Optional

from app.importers.base import ImportResult, ParsedTransaction

logger = logging.getLogger(__name__)

_LOT_TYPES = {"BUY", "VEST"}


class FidelityPreCommitProcessor:
    source: ClassVar[str] = "fidelity_sale"

    def process(self, result: ImportResult, uow) -> ImportResult:
        """Return modified ImportResult with SELL transactions resolved to specific lots."""
        new_transactions: list[ParsedTransaction] = []

        for txn in result.transactions:
            if txn.txn_type != "SELL" or txn.acquisition_date is None:
                new_transactions.append(txn)
                continue

            expanded = self._resolve_sell(txn, uow)
            new_transactions.extend(expanded)

        result.transactions = new_transactions
        return result

    def _resolve_sell(self, sell: ParsedTransaction, uow) -> list[ParsedTransaction]:
        is_stc = sell.acquisition_date == sell.date
        
        # Step 1: sell-to-cover or orphaned
        if is_stc:
            logger.info(
                "FidelityPreCommitProcessor: resolving sell-to-cover for %r acquired %s",
                sell.asset_identifier, sell.acquisition_date,
            )
            
            return self._create_buy_sell_pair(is_stc, sell)
        else:
            # Step 2: find asset in DB
            asset = uow.assets.get_by_identifier(sell.asset_identifier)
            if asset is None:
                logger.warning(
                    "FidelityPreCommitProcessor: no asset found for %r — passing SELL through",
                    sell.asset_identifier,
                )
                return [sell]

            # Step 3: find same-date BUY/VEST lots ordered by id (FIFO among same date)
            all_txns = uow.transactions.list_by_asset(asset.id)
            same_date_lots = sorted(
                [
                    t for t in all_txns
                    if t.date == sell.acquisition_date
                    and self._txn_type_str(t) in _LOT_TYPES
                    and t.lot_id
                ],
                key=lambda t: t.id,
            )

            if same_date_lots:
                return self._split_sell(sell, same_date_lots)

            # No lots found — orphaned sale, create synthetic BUY + SELL
            return self._create_buy_sell_pair(is_stc, sell)

    def _split_sell(self, sell: ParsedTransaction, lots: list) -> list[ParsedTransaction]:
        """FIFO split of sell across same-date lots."""
        remaining = sell.units
        sell_price_per_unit = sell.amount_inr / sell.units if sell.units else 0.0
        partials: list[ParsedTransaction] = []

        for lot in lots:
            if remaining <= 0:
                break
            consumed = min(lot.units, remaining)
            remaining -= consumed

            partial_txn_id = self._partial_txn_id(sell.txn_id, lot.lot_id)
            partials.append(replace(
                sell,
                units=consumed,
                amount_inr=round(sell_price_per_unit * consumed, 4),
                lot_id=lot.lot_id,
                txn_id=partial_txn_id,
            ))

        if remaining > 0:
            logger.warning(
                "FidelityPreCommitProcessor: %s units of %r on %s unmatched by same-date lots — creating fallback buy",
                remaining, sell.asset_identifier, sell.acquisition_date,
            )
            gap_sell = replace(sell, units=remaining, amount_inr=round(sell_price_per_unit * remaining, 4))
            partials.extend(self._create_buy_sell_pair(gap_sell))

        return partials

    def _create_buy_sell_pair(self, is_stc: bool, sell: ParsedTransaction) -> list[ParsedTransaction]:
        """Create a synthetic BUY + the SELL, sharing a fresh lot_id."""
        new_lot_id = str(uuid.uuid4())
        prefix = "fidelity_stc_buy" if is_stc else "fidelity_orphan_buy"
        qty_int = round((sell.units or 0) * 10000)
        raw = f"{prefix}|{sell.asset_identifier}|{sell.acquisition_date.isoformat()}|{qty_int}"
        buy_txn_id = prefix + "_" + hashlib.sha256(raw.encode()).hexdigest()[:16]

        acq_cost = sell.acquisition_cost or 0.0
        acq_forex = sell.acquisition_forex_rate or 1.0
        units = sell.units or 0.0
        price_per_unit_usd = (acq_cost / acq_forex / units) if (acq_forex and units) else 0.0

        if not is_stc:
            logger.warning(
                "FidelityPreCommitProcessor: no matching buy found for %r acquired %s — synthetic lot created",
                sell.asset_identifier, sell.acquisition_date,
            )

        buy = replace(
            sell,
            txn_type="BUY",
            date=sell.acquisition_date,
            amount_inr=-acq_cost,
            price_per_unit=price_per_unit_usd,
            forex_rate=sell.acquisition_forex_rate,
            lot_id=new_lot_id,
            txn_id=buy_txn_id,
            notes=f"Synthetic lot ({'sell-to-cover' if is_stc else 'orphaned sale'})",
            acquisition_date=None,
            acquisition_cost=None,
            acquisition_forex_rate=None,
        )
        sell_out = replace(sell, lot_id=new_lot_id)
        return [buy, sell_out]

    @staticmethod
    def _txn_type_str(txn) -> str:
        t = getattr(txn, "type", None)
        if t is None:
            return str(getattr(txn, "txn_type", ""))
        return t.value if hasattr(t, "value") else str(t)

    @staticmethod
    def _partial_txn_id(original_txn_id: str, lot_id: str) -> str:
        raw = f"fidelity_partial|{original_txn_id}|{lot_id}"
        return "fidelity_partial_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
