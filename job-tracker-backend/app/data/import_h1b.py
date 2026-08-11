"""
One-off / periodic script to import DOL LCA (H1B) disclosure data into the
h1b_sponsors table.

Data source: https://www.dol.gov/agencies/eta/foreign-labor/performance
Download the "LCA Programs" disclosure file for the fiscal year you want
(it's an Excel/CSV file with one row per certified application) and point
this script at it.

Usage:
    python -m app.data.import_h1b --file path/to/LCA_Disclosure_Data_FY2025.xlsx --year 2025

The DOL file's column names shift slightly year to year, so this script
normalizes the columns it needs and ignores the rest rather than assuming
an exact schema.
"""

import argparse
import sys

import pandas as pd
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import H1BSponsor
from app.services.h1b_matcher import normalize_company_name

# Column names as they've historically appeared in DOL disclosure files.
# We match case-insensitively and take the first one found.
EMPLOYER_NAME_CANDIDATES = ["EMPLOYER_NAME", "Employer (Petitioner) Name"]
JOB_TITLE_CANDIDATES = ["JOB_TITLE", "Job Title"]
STATUS_CANDIDATES = ["CASE_STATUS", "Case Status"]


def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower_map = {c.lower(): c for c in df.columns}
    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    return None


def import_file(path: str, fiscal_year: int, db: Session, batch_size: int = 5000) -> int:
    read_fn = pd.read_excel if path.endswith((".xlsx", ".xls")) else pd.read_csv
    df = read_fn(path)

    employer_col = _find_column(df, EMPLOYER_NAME_CANDIDATES)
    title_col = _find_column(df, JOB_TITLE_CANDIDATES)
    status_col = _find_column(df, STATUS_CANDIDATES)

    if not employer_col:
        raise ValueError(
            f"Could not find an employer name column. Available columns: {list(df.columns)}"
        )

    # Aggregate per-employer: total applications + approved count.
    df["_normalized_name"] = df[employer_col].astype(str).map(normalize_company_name)
    df["_approved"] = (
        df[status_col].astype(str).str.upper().eq("CERTIFIED") if status_col else False
    )

    grouped = df.groupby(["_normalized_name", employer_col]).agg(
        total_applications=(employer_col, "count"),
        approved_applications=("_approved", "sum"),
    )
    if title_col:
        sample_titles = df.groupby(employer_col)[title_col].first()
    else:
        sample_titles = {}

    inserted = 0
    batch = []
    for (normalized_name, raw_name), row in grouped.iterrows():
        batch.append(
            H1BSponsor(
                company_name=normalized_name,
                company_name_raw=raw_name,
                fiscal_year=fiscal_year,
                total_applications=int(row["total_applications"]),
                approved_applications=int(row["approved_applications"]),
                job_title_sample=sample_titles.get(raw_name) if title_col else None,
            )
        )
        if len(batch) >= batch_size:
            db.bulk_save_objects(batch)
            db.commit()
            inserted += len(batch)
            batch = []

    if batch:
        db.bulk_save_objects(batch)
        db.commit()
        inserted += len(batch)

    return inserted


def main():
    parser = argparse.ArgumentParser(description="Import DOL H1B disclosure data")
    parser.add_argument("--file", required=True, help="Path to DOL disclosure CSV/XLSX")
    parser.add_argument("--year", required=True, type=int, help="Fiscal year of this file")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        count = import_file(args.file, args.year, db)
        print(f"Imported {count} employer records for FY{args.year}.")
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
