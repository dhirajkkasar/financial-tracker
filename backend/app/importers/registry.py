"""
Importer registry + @register_importer decorator.

Usage:
    @register_importer
    class GrowwCSVImporter(BaseImporter):
        source = "groww"
        asset_type = "STOCK_IN"
        format = "csv"
        ...

Adding a new importer: create the class, apply @register_importer. Done.
No changes to ImporterRegistry or any other file.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.importers.base import BaseImporter

_REGISTRY: dict[tuple[str, str], type] = {}


def register_importer(cls):
    """
    Class decorator that registers an importer by (source, format) key.

    The class must have `source` and `format` class variables defined.
    """
    key = (cls.source, cls.format)
    _REGISTRY[key] = cls
    return cls


class ImporterRegistry:
    """
    Looks up and instantiates importers by (source, format).

    Returns a fresh instance for each call (importers are stateless).
    """

    def get(self, source: str, fmt: str, **init_kwargs) -> "BaseImporter":
        cls = _REGISTRY.get((source, fmt))
        if cls is None:
            available = sorted(_REGISTRY.keys())
            raise ValueError(
                f"No importer for source={source!r} format={fmt!r}. "
                f"Registered: {available}"
            )
        # Resolve the class symbol from its module at runtime. This allows
        # tests to patch the importer class on the module (unittest.mock.patch)
        # and have the registry pick up the patched symbol.
        try:
            import importlib
            mod = importlib.import_module(cls.__module__)
            current = getattr(mod, cls.__name__, cls)
            cls_to_instantiate = current
        except Exception:
            cls_to_instantiate = cls
        return cls_to_instantiate(**init_kwargs)

    def list_registered(self) -> list[tuple[str, str]]:
        """Return all registered (source, format) keys."""
        return sorted(_REGISTRY.keys())
