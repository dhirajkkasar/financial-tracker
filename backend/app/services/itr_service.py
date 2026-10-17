"""ITR service — assemble and persist per-member, per-AY returns.

This phase covers the foundation: prepare (create + seed), read, and update of
the ``ReturnInput`` document. Income assembly and JSON generation are added in
later phases.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from app.engine.itr.ay import ay_to_fy, fy_to_ay
from app.middleware.error_handler import NotFoundError, ValidationError
from app.models.itr_return import ItrReturn
from app.repositories.unit_of_work import IUnitOfWorkFactory, UnitOfWork
from app.schemas.itr_models import ReturnInput

logger = logging.getLogger(__name__)

# Blocks that carry across years unchanged (identity + fixed blocks). These are
# copied into a new AY's return; prior-year income/gains/challans are NOT.
_SEED_BLOCKS = ("address", "bank_accounts", "creation", "regime",
                "residential_status", "dob")


class ItrService:
    def __init__(self, uow_factory: IUnitOfWorkFactory, tax_service=None):
        self._uow_factory = uow_factory
        self._tax_service = tax_service

    # ── prepare / read ─────────────────────────────────────────────────────────

    def prepare(self, member_id: int, fy_label: str) -> ItrReturn:
        """Create (or return the existing) return for member + FY, seeding the
        input document from the member's identity and the prior AY's fixed blocks."""
        try:
            ay_label = fy_to_ay(fy_label)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        with self._uow_factory() as uow:
            member = uow.members.get_by_id(member_id)
            if member is None:
                raise NotFoundError(f"Member {member_id} not found")

            existing = uow.itr_returns.get_by_member_ay(member_id, ay_label)
            if existing is not None:
                return existing

            record = uow.itr_returns.get_or_create(member_id, fy_label, ay_label)

            inp = ReturnInput(
                member_id=member_id,
                fy_label=fy_label,
                ay_label=ay_label,
                pan=member.pan or "",
                name=member.name or "",
            )
            self._seed_fixed_blocks(uow, inp, member_id, ay_label)
            uow.itr_returns.save_input(record.id, inp.model_dump_json())
            return record

    def _seed_fixed_blocks(
        self, uow: UnitOfWork, inp: ReturnInput, member_id: int, ay_label: str
    ) -> None:
        prior_ay = ay_to_fy(ay_label)  # previous AY shares the prior FY's label
        prior = uow.itr_returns.get_by_member_ay(member_id, prior_ay)
        if prior is None or not prior.input_json:
            return
        try:
            prior_input = ReturnInput.model_validate_json(prior.input_json)
        except Exception:  # pragma: no cover - corrupt row, don't block prepare
            logger.warning("Ignoring unparseable prior ReturnInput for member %s", member_id)
            return
        update = {block: getattr(prior_input, block) for block in _SEED_BLOCKS}
        merged = ReturnInput.model_validate(
            {**inp.model_dump(mode="json"), **update}
        )
        for field in ReturnInput.model_fields:
            setattr(inp, field, getattr(merged, field))

    # ── Form 16 ────────────────────────────────────────────────────────────────

    def attach_form16(self, return_id: int, file_bytes: bytes) -> tuple[ReturnInput, list[str]]:
        """Parse a Form 16 PDF and merge it into the return's salary list.

        Deduped by (employer TAN, period): re-uploading the same employer's Form 16
        replaces the prior entry instead of appending a duplicate. Returns the
        updated input document plus the parser's warnings (fields the user must fix).
        """
        from app.engine.form16_parser import parse_form16_pdf

        with self._uow_factory() as uow:
            record = uow.itr_returns.get(return_id)
            if record is None:
                raise NotFoundError(f"ITR return {return_id} not found")
            try:
                summary = parse_form16_pdf(file_bytes)
            except Exception as exc:  # pdfplumber raises a variety of parse errors
                raise ValidationError(f"Could not read Form 16 PDF: {exc}") from exc
            current = self._load_input(record)
            key = (summary.employer_tan, summary.period_from, summary.period_to)
            for idx, existing in enumerate(current.salary):
                if (existing.employer_tan, existing.period_from, existing.period_to) == key:
                    current.salary[idx] = summary
                    break
            else:
                current.salary.append(summary)
            uow.itr_returns.save_input(return_id, current.model_dump_json())
            return current, list(summary.warnings)

    def _load_input(self, record: ItrReturn) -> ReturnInput:
        if not record.input_json:
            return ReturnInput(
                member_id=record.member_id,
                fy_label=record.fy_label,
                ay_label=record.ay_label,
            )
        return ReturnInput.model_validate_json(record.input_json)

    # ── assemble ──────────────────────────────────────────────────────────────

    def assemble(self, return_id: int):
        """Build the ITR draft from portfolio gains + the return input document."""
        from app.services.itr_assembler import assemble_draft

        if self._tax_service is None:
            raise RuntimeError("ItrService.assemble requires a TaxService")
        record = self.get(return_id)
        if record is None:
            raise NotFoundError(f"ITR return {return_id} not found")
        inp = self.get_input(return_id)
        summary = self._tax_service.get_tax_summary(
            record.fy_label, member_id=record.member_id
        )
        draft = assemble_draft(inp, summary)
        with self._uow_factory() as uow:
            uow.itr_returns.save_draft(
                return_id, json.dumps(draft.to_json_dict()), form_type=draft.form
            )
        return draft

    def get_available_fys(self) -> list[str]:
        """Sorted FY labels that have a tax-rules config file."""
        config_dir = Path("app/config/tax_rates")
        return sorted(
            p.stem for p in config_dir.glob("*.yaml") if p.stem != "__init__"
        )

    def get(self, return_id: int) -> Optional[ItrReturn]:
        with self._uow_factory() as uow:
            return uow.itr_returns.get(return_id)

    def list_for_member(self, member_id: int) -> list[ItrReturn]:
        with self._uow_factory() as uow:
            return uow.itr_returns.list_by_member(member_id)

    def get_input(self, return_id: int) -> ReturnInput:
        with self._uow_factory() as uow:
            record = uow.itr_returns.get(return_id)
            if record is None:
                raise NotFoundError(f"ITR return {return_id} not found")
            return self._load_input(record)

    def get_draft(self, return_id: int):
        """The persisted :class:`ReturnDraft`, or ``None`` if never assembled."""
        from app.services.itr_assembler import ReturnDraft

        record = self.get(return_id)
        if record is None:
            raise NotFoundError(f"ITR return {return_id} not found")
        if not record.draft_json:
            return None
        return ReturnDraft(**json.loads(record.draft_json))

    # ── update ─────────────────────────────────────────────────────────────────

    def update_input(self, return_id: int, patch: dict) -> ReturnInput:
        """Deep-merge ``patch`` into the stored input document and persist it."""
        with self._uow_factory() as uow:
            record = uow.itr_returns.get(return_id)
            if record is None:
                raise NotFoundError(f"ITR return {return_id} not found")
            current = (
                json.loads(record.input_json)
                if record.input_json
                else {
                    "member_id": record.member_id,
                    "fy_label": record.fy_label,
                    "ay_label": record.ay_label,
                }
            )
            merged = ReturnInput.model_validate(_deep_merge(current, patch))
            uow.itr_returns.save_input(return_id, merged.model_dump_json())
            return merged


def _deep_merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out
