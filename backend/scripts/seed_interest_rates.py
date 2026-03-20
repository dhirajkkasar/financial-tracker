"""Seed PPF and EPF interest rates. Idempotent."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.interest_rate import InterestRateHistory
from datetime import date

PPF_RATES = [
    # (effective_from, effective_to, rate_pct, fy_label)
    (date(2000, 4, 1), date(2001, 3, 31), 11.0, "FY2000-01"),
    (date(2001, 4, 1), date(2002, 3, 31), 9.5, "FY2001-02"),
    (date(2002, 4, 1), date(2003, 3, 31), 9.0, "FY2002-03"),
    (date(2003, 4, 1), date(2011, 11, 30), 8.0, "FY2003-11"),
    (date(2011, 12, 1), date(2012, 3, 31), 8.6, "FY2011-12"),
    (date(2012, 4, 1), date(2013, 3, 31), 8.8, "FY2012-13"),
    (date(2013, 4, 1), date(2016, 3, 31), 8.7, "FY2013-16"),
    (date(2016, 4, 1), date(2016, 9, 30), 8.1, "FY2016-H1"),
    (date(2016, 10, 1), date(2017, 3, 31), 8.0, "FY2016-H2"),
    (date(2017, 4, 1), date(2019, 12, 31), 7.9, "FY2017-19"),
    (date(2020, 1, 1), date(2020, 3, 31), 7.9, "FY2019-20-Q4"),
    (date(2020, 4, 1), date(2021, 3, 31), 7.1, "FY2020-21"),
    (date(2021, 4, 1), date(2023, 3, 31), 7.1, "FY2021-23"),
    (date(2023, 4, 1), None, 7.1, "FY2023-present"),
]

EPF_RATES = [
    (date(2000, 4, 1), date(2001, 3, 31), 11.0, "FY2000-01"),
    (date(2001, 4, 1), date(2002, 3, 31), 9.5, "FY2001-02"),
    (date(2002, 4, 1), date(2004, 3, 31), 9.5, "FY2002-04"),
    (date(2004, 4, 1), date(2010, 3, 31), 8.5, "FY2004-10"),
    (date(2010, 4, 1), date(2011, 3, 31), 9.5, "FY2010-11"),
    (date(2011, 4, 1), date(2012, 3, 31), 8.25, "FY2011-12"),
    (date(2012, 4, 1), date(2013, 3, 31), 8.5, "FY2012-13"),
    (date(2013, 4, 1), date(2014, 3, 31), 8.75, "FY2013-14"),
    (date(2014, 4, 1), date(2015, 3, 31), 8.75, "FY2014-15"),
    (date(2015, 4, 1), date(2016, 3, 31), 8.8, "FY2015-16"),
    (date(2016, 4, 1), date(2017, 3, 31), 8.65, "FY2016-17"),
    (date(2017, 4, 1), date(2018, 3, 31), 8.55, "FY2017-18"),
    (date(2018, 4, 1), date(2019, 3, 31), 8.65, "FY2018-19"),
    (date(2019, 4, 1), date(2020, 3, 31), 8.5, "FY2019-20"),
    (date(2020, 4, 1), date(2021, 3, 31), 8.5, "FY2020-21"),
    (date(2021, 4, 1), date(2022, 3, 31), 8.1, "FY2021-22"),
    (date(2022, 4, 1), date(2023, 3, 31), 8.15, "FY2022-23"),
    (date(2023, 4, 1), None, 8.25, "FY2023-present"),
]


def seed(db):
    for effective_from, effective_to, rate, fy in PPF_RATES:
        existing = db.query(InterestRateHistory).filter_by(
            instrument="PPF", effective_from=effective_from
        ).first()
        if not existing:
            db.add(InterestRateHistory(
                instrument="PPF", rate_pct=rate,
                effective_from=effective_from, effective_to=effective_to,
                fy_label=fy
            ))
    for effective_from, effective_to, rate, fy in EPF_RATES:
        existing = db.query(InterestRateHistory).filter_by(
            instrument="EPF", effective_from=effective_from
        ).first()
        if not existing:
            db.add(InterestRateHistory(
                instrument="EPF", rate_pct=rate,
                effective_from=effective_from, effective_to=effective_to,
                fy_label=fy
            ))
    db.commit()
    print("Interest rates seeded.")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
