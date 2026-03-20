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
        "PAN": "BQEPK6167M",
        "UID (Aadhaar)": "323027405718",
        "Blood Group": "A+",
        "Passport No.": "W1283885 (new) / J3592872 (old)",
        "Passport Expiry": "20/06/2032",
        "Driving License No.": "MH1520080052961",
        "DL Expiry": "10/12/2028",
        "Mobile Numbers": "8956223684 (Jio) / 7875311611 (BSNL)",
        "Voters ID": "ZXS6393466",
    })

    # ── Employment Details ────────────────────────────────────────────────────
    _upsert(db, ImportantDataCategory.IDENTITY, "Employment Details", {
        "Employee ID": "113135637",
        "Work Email": "kasardk@amazon.com",
        "UAN": "100932718301",
        "EPF No.": "BGBNG00268580000306940",
        "PRAN (NPS)": "110144447289",
    }, notes="Employment Details")

    # ── Home Utilities ────────────────────────────────────────────────────────
    _upsert(db, ImportantDataCategory.OTHER, "Home Utilities", {
        "Electricity Account No.": "170400003401",
        "Property Tax ID": "O/A/01/03574042",
        "Cable TV Account No.": "1298271642",
        "Cable TV Provider": "Tata Sky",
        "OTT Mobile No.": "8956223684",
    }, notes="Home Utilities Details")

    # ── Property Details ──────────────────────────────────────────────────────
    _upsert(db, ImportantDataCategory.OTHER, "Venezia Co-op Housing Society (Residential)", {
        "Address": "B-901, SN 45/1, Near Pune-Banglore Highway, Baner, Pune 411045",
        "Date Acquired": "09/11/2020",
        "Index 2 No.": "11834/2020",
        "Owners": "Dhiraj Kamlakar Kasar / Manisha Dhiraj Kasar",
        "Home Loan (642166842)": "₹50,00,000 — Closed",
        "Insurance Loan (656846651)": "₹1,12,000 — Closed",
        "Top-up Loan (702991012)": "₹25,00,000 — Open | EMI ₹32,255",
        "Loan Bank": "HDFC",
    }, notes="Property Details")

    _upsert(db, ImportantDataCategory.OTHER, "VTP Altitude (Commercial)", {
        "Address": "Office No. 618, SR.NO 18/6, Village Thergaon, Taluka Mulashi, Pune - 411033",
        "Date Acquired": "27/06/2024",
        "Index 2 No.": "15153/2024",
        "Owner": "Dhiraj Kamlakar Kasar HUF",
        "Loan": "None",
    }, notes="Property Details")

    # ── Bank Accounts ─────────────────────────────────────────────────────────
    _upsert(db, ImportantDataCategory.BANK, "HDFC", {
        "Account No.": "7941610064486",
        "Type": "Savings (Salary)",
        "IFSC": "HDFC0000794",
        "Branch": "Hinjewadi Phase 2, Pune",
        "Customer ID / Login": "35697166",
        "Nominee": "Manisha Kasar",
    })

    _upsert(db, ImportantDataCategory.BANK, "SBI", {
        "Account No.": "30466324987",
        "Type": "Savings",
        "IFSC": "SBIN0013547",
        "Branch": "Pashan Near Balaji Square, Pune",
        "Customer ID": "85297265080",
        "Login ID": "dhirajkasar",
        "Nominee": "Kamlakar Kasar",
    })

    _upsert(db, ImportantDataCategory.BANK, "SBI (PPF)", {
        "Account No.": "32256576916",
        "Type": "PPF",
        "Branch": "Treasury Branch, Nashik",
        "Customer ID": "85297265080",
        "Login ID": "dhirajkasar",
        "Nominee": "Kamlakar Kasar",
    })

    _upsert(db, ImportantDataCategory.BANK, "ICICI (HUF)", {
        "Account No.": "539701000207",
        "Type": "HUF (Dhiraj Kamlakar Kasar HUF)",
        "IFSC": "ICIC0005397",
        "Branch": "Pancard Club Road, Baner, Pune",
        "Customer ID / Login": "B597625786",
        "Nominee": "Manisha Kasar",
    })

    # ── Insurance Details ─────────────────────────────────────────────────────
    _upsert(db, ImportantDataCategory.INSURANCE, "ICICI Prudential - iProtect Smart", {
        "Insured": "Dhiraj Kamlakar Kasar",
        "Type": "Life Insurance",
        "Policy No.": "A8598651",
        "Annual Premium": "₹14,255",
        "Due Date": "4th November",
        "Sum Assured": "₹1,00,00,000",
        "CKYC": "60099997241440",
    })

    _upsert(db, ImportantDataCategory.INSURANCE, "Vehicle Insurance - Tata Nexon", {
        "Insured": "Dhiraj Kamlakar Kasar",
        "Type": "Vehicle Insurance",
    })

    _upsert(db, ImportantDataCategory.INSURANCE, "Vehicle Insurance - TVS Jupiter", {
        "Insured": "Dhiraj Kamlakar Kasar",
        "Type": "Vehicle Insurance",
    })

    _upsert(db, ImportantDataCategory.INSURANCE, "Vehicle Insurance - Bajaj Pulsar", {
        "Insured": "Dhiraj Kamlakar Kasar",
        "Type": "Vehicle Insurance",
    })

    _upsert(db, ImportantDataCategory.INSURANCE, "Property Insurance", {
        "Insured": "Dhiraj Kamlakar Kasar",
        "Type": "Property Insurance",
    })

    _upsert(db, ImportantDataCategory.INSURANCE, "Health Insurance (Self & Family)", {
        "Insured": "Dhiraj Kamlakar Kasar / Manisha Kasar / Arush Kasar",
        "Type": "Health Insurance",
    })

    _upsert(db, ImportantDataCategory.INSURANCE, "Health Insurance (Parents)", {
        "Insured": "Kamlakar Kasar / Surekha Kasar",
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
