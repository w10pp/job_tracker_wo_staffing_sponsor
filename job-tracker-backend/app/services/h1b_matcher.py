"""
Matches a job posting's company name against the imported H1B disclosure
data (see app/data/import_h1b.py) using normalized + fuzzy string matching.

This is a *factual* signal (has this company actually filed H1B petitions
in recent years?) that gets combined with JD text heuristics and an LLM
judgment in services/ai_classifier.py to produce a final sponsorship
verdict.
"""

import re
from dataclasses import dataclass

from rapidfuzz import fuzz, process
from sqlalchemy.orm import Session

from app.models import H1BSponsor

# Common corporate suffixes that make exact matching fail
# (e.g. "Google LLC" vs "Google Inc" vs "Google").
_SUFFIX_PATTERN = re.compile(
    r"\b(inc|llc|ltd|corp|corporation|co|company|group|holdings|the)\.?\b",
    flags=re.IGNORECASE,
)


def normalize_company_name(name: str) -> str:
    name = name.lower()
    name = _SUFFIX_PATTERN.sub("", name)
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


@dataclass
class H1BMatchResult:
    matched: bool
    confidence: float  # 0.0 - 1.0
    recent_years: list[int]
    matched_company_name: str | None = None


def match_company_to_h1b(
    db: Session, company_name: str, min_score: int = 88
) -> H1BMatchResult:
    """
    Fuzzy-matches `company_name` against the h1b_sponsors table.

    NOTE: this does a full-table fetch of distinct normalized names for
    simplicity. For a production-scale dataset (DOL data has 500k+ rows/yr)
    you'd want to pre-aggregate distinct normalized company names into a
    lookup table at import time instead of querying per-request.
    """
    target = normalize_company_name(company_name)
    if not target:
        return H1BMatchResult(matched=False, confidence=0.0, recent_years=[])

    rows = (
        db.query(H1BSponsor.company_name, H1BSponsor.fiscal_year)
        .filter(H1BSponsor.company_name.like(f"{target[:4]}%"))
        .all()
    )

    if not rows:
        return H1BMatchResult(matched=False, confidence=0.0, recent_years=[])

    candidates = {r.company_name for r in rows}
    best = process.extractOne(target, list(candidates), scorer=fuzz.WRatio)

    if best is None or best[1] < min_score:
        return H1BMatchResult(matched=False, confidence=0.0, recent_years=[])

    matched_name, score, _ = best
    years = sorted({r.fiscal_year for r in rows if r.company_name == matched_name})

    return H1BMatchResult(
        matched=True,
        confidence=round(score / 100, 2),
        recent_years=years,
        matched_company_name=matched_name,
    )
