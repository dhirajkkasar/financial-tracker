"""ITR JSON builders, registered by ``(form, ay)``.

Importing this package registers the available builders.
"""
from app.engine.itr.builders import itr2_ay2026  # noqa: F401  (registration side-effect)
from app.engine.itr.builders.base import (
    ItrBuilder,
    UnsupportedFormError,
    get_builder,
    register_builder,
    supported_forms,
)

__all__ = [
    "ItrBuilder",
    "UnsupportedFormError",
    "get_builder",
    "register_builder",
    "supported_forms",
]
