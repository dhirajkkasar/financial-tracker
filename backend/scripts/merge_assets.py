"""
One-time script to merge duplicate assets caused by BSE/NSE ticker name divergence.

Merges:
  ASHOK LEYL. (BSE, ids 35 + 36) → ASHOKLEY (NSE, id 39, ISIN INE208A01029)
  GREAVESCOT  (BSE, ids 31 + 32) → GREAVESCOT (NSE, id 48, ISIN INE224A01026)

After merging, recomputes net_units for each canonical asset and marks inactive if net=0.

Usage (server NOT required — direct DB access):
  cd backend && uv run python scripts/merge_assets.py --confirm
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.asset import Asset
from app.models.transaction import Transaction, TransactionType

_UNIT_ADD_TYPES = {"BUY", "SIP", "VEST", "BONUS"}
_UNIT_SUB_TYPES = {"SELL", "REDEMPTION"}

MERGES = [
    {
        "label": "ASHOKLEY",
        "canonical_id": 39,
        "source_ids": [35, 36],
    },
    {
        "label": "GREAVESCOT",
        "canonical_id": 48,
        "source_ids": [31, 32],
    },
]


def merge_and_deactivate(db, label: str, canonical_id: int, source_ids: list[int], dry_run: bool):
    canonical = db.query(Asset).get(canonical_id)
    if not canonical:
        print(f"  ERROR: canonical asset {canonical_id} not found")
        return

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Merging {label}")
    print(f"  Canonical: id={canonical_id} name={canonical.name} isin={canonical.identifier}")

    for src_id in source_ids:
        src = db.query(Asset).get(src_id)
        if not src:
            print(f"  SKIP: source asset {src_id} not found")
            continue

        txns = db.query(Transaction).filter(Transaction.asset_id == src_id).all()
        print(f"  Source: id={src_id} name={src.name} — {len(txns)} transactions to move")

        if not dry_run:
            for t in txns:
                # Check for txn_id collision on canonical asset
                existing = db.query(Transaction).filter(
                    Transaction.txn_id == t.txn_id,
                    Transaction.asset_id == canonical_id,
                ).first()
                if existing:
                    print(f"    SKIP dup txn_id={t.txn_id}")
                    continue
                t.asset_id = canonical_id
                print(f"    Moved txn {t.id} ({t.type.value} {t.date} units={t.units})")

            # Mark source asset inactive and clear name to avoid future confusion
            src.is_active = False
            src.name = f"[MERGED→{canonical_id}] {src.name}"
            print(f"  Marked id={src_id} inactive and renamed")

    if not dry_run:
        db.flush()

        # Recompute net_units and update is_active on canonical
        all_txns = db.query(Transaction).filter(Transaction.asset_id == canonical_id).all()
        net_units = sum(
            (t.units or 0.0) if t.type.value in _UNIT_ADD_TYPES
            else -(t.units or 0.0) if t.type.value in _UNIT_SUB_TYPES
            else 0.0
            for t in all_txns
        )
        print(f"  net_units after merge: {net_units:.4f}")
        if net_units <= 1e-6 and net_units >= -1e-6:
            canonical.is_active = False
            print(f"  → Marked canonical {canonical_id} INACTIVE (net_units ≈ 0)")
        elif net_units < -1e-6:
            print(f"  WARNING: net_units={net_units:.4f} still negative — data gap remains")
        else:
            print(f"  → Canonical stays ACTIVE (net_units={net_units:.4f})")


def main():
    parser = argparse.ArgumentParser(description="Merge duplicate BSE/NSE assets")
    parser.add_argument("--confirm", action="store_true", help="Actually perform the merge (default: dry run)")
    args = parser.parse_args()

    dry_run = not args.confirm

    if dry_run:
        print("DRY RUN — pass --confirm to execute")

    db = SessionLocal()
    try:
        for m in MERGES:
            merge_and_deactivate(db, m["label"], m["canonical_id"], m["source_ids"], dry_run)

        if not dry_run:
            db.commit()
            print("\n✓ Committed")
        else:
            print("\n(No changes written — rerun with --confirm)")
    except Exception as e:
        db.rollback()
        print(f"\nERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
