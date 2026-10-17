"""Builder registry: ``(form, ay) -> builder instance``."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

from app.schemas.itr_models import ReturnInput
from app.services.itr_assembler import ReturnDraft


class UnsupportedFormError(ValueError):
    """No builder is registered for this form + assessment year."""


class ItrBuilder(ABC):
    form: str = ""
    ay_label: str = ""

    @abstractmethod
    def build(
        self,
        draft: ReturnDraft,
        input_doc: ReturnInput,
        *,
        generated_on: Optional[date] = None,
    ) -> dict:
        """Return the ITR JSON document (``{"ITR": {...}}``)."""


_REGISTRY: dict[tuple[str, str], ItrBuilder] = {}


def register_builder(cls: type[ItrBuilder]) -> type[ItrBuilder]:
    _REGISTRY[(cls.form, cls.ay_label)] = cls()
    return cls


def get_builder(form: str, ay_label: str) -> ItrBuilder:
    try:
        return _REGISTRY[(form, ay_label)]
    except KeyError as exc:
        raise UnsupportedFormError(
            f"No ITR builder for form {form!r} AY {ay_label!r}"
        ) from exc


def supported_forms() -> list[tuple[str, str]]:
    return sorted(_REGISTRY)
