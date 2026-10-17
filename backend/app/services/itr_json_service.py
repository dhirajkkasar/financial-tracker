"""Generate the final ITR JSON from an assembled draft, then validate it.

The generator is the only place that turns a reviewable draft into a file. It
refuses to write anything unless the document passes both the structural schema
check and the semantic tie-outs — so a returned/exported file is always one the
Common Offline Utility can import.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.engine.itr.builders import UnsupportedFormError, get_builder
from app.engine.itr.schema_loader import schema_version as _schema_version
from app.engine.itr.schema_validation import ValidationReport, validate_itr_json
from app.middleware.error_handler import NotFoundError, ValidationError
from app.repositories.unit_of_work import IUnitOfWorkFactory

# The form selector emits "ITR2"; the builder registry keys on the printed name.
_FORM_LABELS = {"ITR2": "ITR-2", "ITR1": "ITR-1"}


@dataclass
class GenerateResult:
    document: dict
    report: ValidationReport
    schema_version: str
    form: str


class ItrJsonService:
    def __init__(self, uow_factory: IUnitOfWorkFactory, itr_service):
        self._uow_factory = uow_factory
        self._itr = itr_service

    # ── building ──────────────────────────────────────────────────────────────

    def get_record(self, return_id: int):
        record = self._itr.get(return_id)
        if record is None:
            raise NotFoundError(f"ITR return {return_id} not found")
        return record

    def _form_label(self, form_type: str) -> str:
        label = _FORM_LABELS.get(form_type)
        if label is None:
            raise ValidationError(f"Unknown form type {form_type!r}")
        return label

    def build_document(self, return_id: int) -> tuple[dict, str, str]:
        """(document, form label, ay label) — no persistence."""
        record = self._itr.get(return_id)
        if record is None:
            raise NotFoundError(f"ITR return {return_id} not found")
        draft = self._itr.get_draft(return_id)
        if draft is None:
            raise ValidationError(
                "Assemble the return (POST .../assemble) before generating the JSON"
            )
        form = self._form_label(record.form_type)
        try:
            builder = get_builder(form, record.ay_label)
        except UnsupportedFormError as exc:
            raise ValidationError(str(exc)) from exc
        inp = self._itr.get_input(return_id)
        return builder.build(draft, inp), form, record.ay_label

    # ── public operations ─────────────────────────────────────────────────────

    def validate(self, return_id: int) -> ValidationReport:
        doc, form, ay = self.build_document(return_id)
        return validate_itr_json(doc, ay, form)

    def generate(self, return_id: int) -> GenerateResult:
        doc, form, ay = self.build_document(return_id)
        report = validate_itr_json(doc, ay, form)
        if not report.ok:
            raise ValidationError(
                f"Generated {form} failed validation; nothing was written:\n{report.render()}"
            )
        version = _schema_version(ay, form)
        with self._uow_factory() as uow:
            uow.itr_returns.save_output(
                return_id, json.dumps(doc, indent=2), schema_version=version
            )
        return GenerateResult(
            document=doc, report=report, schema_version=version, form=form
        )

    def get_output(self, return_id: int) -> dict:
        record = self._itr.get(return_id)
        if record is None:
            raise NotFoundError(f"ITR return {return_id} not found")
        if not record.output_json:
            raise NotFoundError(
                f"ITR return {return_id} has no generated JSON — POST .../generate first"
            )
        return json.loads(record.output_json)
