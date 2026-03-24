"""
Seed personal info data from CSV.
Idempotent — skips entries that already exist (matched by category + label).

Usage:
    cd backend
    python scripts/seed_personal_info.py
"""
import sys, os, json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.important_data import ImportantData, ImportantDataCategory


def _upsert(db, category: ImportantDataCategory, label: str, fields: dict, notes: str | None = None):
    existing = db.query(ImportantData).filter_by(category=category, label=label).first()
    if existing:
        print(f"  skip  {label}")
        return
    obj = ImportantData(
        category=category,
        label=label,
        fields_json=json.dumps(fields),
        notes=notes,
        created_at=datetime.utcnow(),
    )
    db.add(obj)
    print(f"  insert {label}")


def seed(db):
    # ── Personal Details ──────────────────────────────────────────────────────
    _upsert(db, ImportantDataCategory.IDENTITY, "Personal Details", {
        "PAN": "AAAAA0000A",
        "UID (Aadhaar)": "0000 0000 0000",
        "Blood Group": "O+",
        "Passport No.": "A0000000",
        "Passport Expiry": "01/01/2030",
        "Driving License No.": "MH00000000000000",
        "DL Expiry": "01/01/2030",
        "Mobile Numbers": "9000000000 (Primary) / 9000000001 (Secondary)",
        "Voters ID": "ABC0000000",
    })

    # ── Employment Details ────────────────────────────────────────────────────
    _upsert(db, ImportantDataCategory.IDENTITY, "Employment Details", {
        "Employee ID": "EMP000000",
        "Work Email": "john.doe@example.com",
        "UAN": "100000000000",
        "EPF No.": "AAAAA00000000000000000",
        "PRAN (NPS)": "110000000000",
    }, notes="Employment Details")

    # ── Home Utilities ────────────────────────────────────────────────────────
    _upsert(db, ImportantDataCategory.OTHER, "Home Utilities", {
        "Electricity Account No.": "000000000000",
        "Property Tax ID": "A/A/00/00000000",
        "Cable TV Account No.": "0000000000",
        "Cable TV Provider": "Cable Provider Name",
        "OTT Mobile No.": "9000000000",
    }, notes="Home Utilities Details")

    # ── Property Details ──────────────────────────────────────────────────────
    _upsert(db, ImportantDataCategory.OTHER, "Sample Residential Property", {
        "Address": "Flat No. 101, Sample Society, City - 400001",
        "Date Acquired": "01/01/2020",
        "Index 2 No.": "00000/2020",
        "Owners": "John Doe / Jane Doe",
        "Home Loan (000000001)": "₹50,00,000 — Closed",
        "Top-up Loan (000000002)": "₹10,00,000 — Open | EMI ₹15,000",
        "Loan Bank": "Sample Bank",
    }, notes="Property Details")

    _upsert(db, ImportantDataCategory.OTHER, "Sample Commercial Property", {
        "Address": "Office No. 201, Sample Plaza, City - 400002",
        "Date Acquired": "01/01/2024",
        "Index 2 No.": "00000/2024",
        "Owner": "John Doe HUF",
        "Loan": "None",
    }, notes="Property Details")

    # ── Bank Accounts ─────────────────────────────────────────────────────────
    _upsert(db, ImportantDataCategory.BANK, "HDFC", {
        "Account No.": "0000000000000",
        "Type": "Savings (Salary)",
        "IFSC": "HDFC0000000",
        "Branch": "Sample Branch, City",
        "Customer ID / Login": "00000000",
        "Nominee": "Jane Doe",
    })

    _upsert(db, ImportantDataCategory.BANK, "SBI", {
        "Account No.": "00000000000",
        "Type": "Savings",
        "IFSC": "SBIN0000000",
        "Branch": "Sample Branch, City",
        "Customer ID": "00000000000",
        "Login ID": "johndoe",
        "Nominee": "John Doe Sr.",
    })

    _upsert(db, ImportantDataCategory.BANK, "SBI (PPF)", {
        "Account No.": "00000000000",
        "Type": "PPF",
        "Branch": "Treasury Branch, City",
        "Customer ID": "00000000000",
        "Login ID": "johndoe",
        "Nominee": "John Doe Sr.",
    })

    _upsert(db, ImportantDataCategory.BANK, "ICICI (HUF)", {
        "Account No.": "000000000000",
        "Type": "HUF (John Doe HUF)",
        "IFSC": "ICIC0000000",
        "Branch": "Sample Branch, City",
        "Customer ID / Login": "A000000000",
        "Nominee": "Jane Doe",
    })

    # ── Insurance Details ─────────────────────────────────────────────────────
    _upsert(db, ImportantDataCategory.INSURANCE, "ICICI Prudential - iProtect Smart", {
        "Insured": "John Doe",
        "Type": "Life Insurance",
        "Policy No.": "A0000000",
        "Annual Premium": "₹00,000",
        "Due Date": "1st January",
        "Sum Assured": "₹1,00,00,000",
        "CKYC": "00000000000000",
    })

    _upsert(db, ImportantDataCategory.INSURANCE, "Vehicle Insurance - Car", {
        "Insured": "John Doe",
        "Type": "Vehicle Insurance",
    })

    _upsert(db, ImportantDataCategory.INSURANCE, "Vehicle Insurance - Two Wheeler 1", {
        "Insured": "John Doe",
        "Type": "Vehicle Insurance",
    })

    _upsert(db, ImportantDataCategory.INSURANCE, "Vehicle Insurance - Two Wheeler 2", {
        "Insured": "John Doe",
        "Type": "Vehicle Insurance",
    })

    _upsert(db, ImportantDataCategory.INSURANCE, "Property Insurance", {
        "Insured": "John Doe",
        "Type": "Property Insurance",
    })

    _upsert(db, ImportantDataCategory.INSURANCE, "Health Insurance (Self & Family)", {
        "Insured": "John Doe / Jane Doe / Child",
        "Type": "Health Insurance",
    })

    _upsert(db, ImportantDataCategory.INSURANCE, "Health Insurance (Parents)", {
        "Insured": "John Doe Sr. / Jane Doe Sr.",
        "Type": "Health Insurance",
    })

    # ── Demat / Trading / MF Accounts ────────────────────────────────────────
    _upsert(db, ImportantDataCategory.ACCOUNT, "Zerodha", {"Type": "Demat / Trading"})
    _upsert(db, ImportantDataCategory.ACCOUNT, "Kuvera", {"Type": "Mutual Fund Platform"})
    _upsert(db, ImportantDataCategory.ACCOUNT, "ICICI Direct", {"Type": "Demat / Trading / MF"})

    # ── Mutual Fund AMCs ──────────────────────────────────────────────────────
    for amc in ["Parag Parikh", "UTI", "Kotak", "Motilal Oswal", "Navi", "HDFC"]:
        _upsert(db, ImportantDataCategory.MF_FOLIO, amc, {"AMC": amc})

    db.commit()
    print("Done.")


if __name__ == "__main__":
    with SessionLocal() as db:
        seed(db)
