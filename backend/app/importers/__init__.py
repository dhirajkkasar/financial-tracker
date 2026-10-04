"""
Importer module - all submodules must be imported for decorators to register importers.
"""
# Import all importer classes to trigger @register_importer decorators
from app.importers.base import ValidationResult
from app.importers.zerodha_importer import ZerodhaImporter
from app.importers.cas_importer import CASImporter
from app.importers.nps_csv_importer import NPSImporter
from app.importers.ppf_csv_importer import PPFCSVImporter
from app.importers.epf_pdf_importer import EPFPDFImporter
from app.importers.fidelity_lots_importer import FidelityOpenLotsImporter
from app.importers.fidelity_lots_importer import FidelityClosedLotsImporter
from app.importers.ibkr_csv_importer import IBKRTradesImporter

__all__ = [
    "ZerodhaImporter",
    "CASImporter",
    "NPSImporter",
    "PPFCSVImporter",
    "EPFPDFImporter",
    "FidelityOpenLotsImporter",
    "FidelityClosedLotsImporter",
    "IBKRTradesImporter",
    "ValidationResult",
]
