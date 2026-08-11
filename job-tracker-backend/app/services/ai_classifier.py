"""
Core screening logic for a job posting: is this a staffing/agency posting,
and does this employer sponsor visas?

Design: layered signals, cheapest/most-reliable first, LLM as a fallback
for ambiguous cases rather than the sole source of truth.

  Staffing detection:
    1. Company name vs known blocklist (exact/fuzzy)      -> fast, free
    2. JD keyword heuristics ("client site", "our client
       is seeking", "W2 contract", "third-party placement") -> fast, free
    3. LLM classification                                   -> fallback

  Sponsorship detection:
    1. H1B historical filing data (factual)                 -> fast, free
    2. JD keyword heuristics ("no sponsorship", "must be
       a US citizen", "green card holders only")            -> fast, free
    3. LLM classification                                   -> fallback

  Both dimensions are classified in a single LLM call (when needed) to
  save on latency/cost.
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from anthropic import Anthropic
from sqlalchemy.orm import Session

from app.models import SponsorshipStatus
from app.services.h1b_matcher import match_company_to_h1b

_client: Optional[Anthropic] = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


STAFFING_KEYWORDS = [
    r"our client is seeking",
    r"client site",
    r"w-?2 contract",
    r"third[- ]party placement",
    r"c2c\b",
    r"corp[- ]to[- ]corp",
    r"one of our clients",
    r"staffing agency",
    r"on behalf of our client",
]

NO_SPONSOR_KEYWORDS = [
    r"no sponsorship",
    r"unable to sponsor",
    r"must be a? ?u\.?s\.? citizen",
    r"green card holders? only",
    r"active security clearance required",
    r"not able to provide sponsorship",
    r"visa sponsorship is not available",
]


@dataclass
class ScreeningResult:
    is_staffing: bool
    staffing_confidence: float
    staffing_reason: str

    sponsorship_status: SponsorshipStatus
    sponsorship_confidence: float
    sponsorship_reason: str

    h1b_sponsor_match: bool
    h1b_match_confidence: float
    h1b_recent_years: list[int]

    signals: dict = field(default_factory=dict)


def _keyword_hit(text: str, patterns: list[str]) -> Optional[str]:
    lowered = text.lower()
    for pattern in patterns:
        if re.search(pattern, lowered):
            return pattern
    return None


def _llm_classify(company_name: str, position_title: str, job_description: str) -> dict:
    """
    Single structured LLM call used only when rule-based signals are
    inconclusive. Returns a dict with the same shape as the JSON schema
    documented in the module docstring.
    """
    prompt = f"""You are screening a job posting for two things. Respond with ONLY a JSON object, no other text.

Company: {company_name}
Title: {position_title}
Job Description:
{job_description[:4000]}

Determine:
1. is_staffing: true if this posting is from a staffing/recruiting agency placing
   a candidate at a third-party client, rather than a direct employer. Look for
   language like "our client", contract-to-hire via an agency, or the poster's
   business clearly being a staffing firm rather than the company doing the hiring.
2. sponsorship_status: one of "sponsors", "citizen_pr_only", "unclear" - based on
   whether the JD indicates visa sponsorship is available, explicitly restricted
   to citizens/green card holders, or not mentioned either way.

Respond with exactly this JSON shape:
{{
  "is_staffing": true/false,
  "staffing_confidence": 0.0-1.0,
  "staffing_reason": "one sentence",
  "sponsorship_status": "sponsors" | "citizen_pr_only" | "unclear",
  "sponsorship_confidence": 0.0-1.0,
  "sponsorship_reason": "one sentence"
}}"""

    response = get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    text = re.sub(r"^```json|```$", "", text, flags=re.MULTILINE).strip()
    return json.loads(text)


def screen_posting(
    db: Session,
    company_name: str,
    position_title: str,
    job_description: str,
    blocklist_names: set[str],
) -> ScreeningResult:
    signals: dict = {}

    # --- Staffing: rule layer ---
    normalized_company = company_name.strip().lower()
    staffing_from_blocklist = normalized_company in blocklist_names
    signals["blocklist_match"] = staffing_from_blocklist

    staffing_keyword_hit = _keyword_hit(job_description, STAFFING_KEYWORDS)
    signals["staffing_keyword_hit"] = staffing_keyword_hit

    # --- Sponsorship: H1B factual signal ---
    h1b_result = match_company_to_h1b(db, company_name)
    signals["h1b_history_match"] = h1b_result.matched
    signals["h1b_recent_years"] = h1b_result.recent_years

    no_sponsor_hit = _keyword_hit(job_description, NO_SPONSOR_KEYWORDS)
    signals["no_sponsor_keyword_hit"] = no_sponsor_hit

    rules_conclusive = staffing_from_blocklist or staffing_keyword_hit
    sponsorship_conclusive = h1b_result.matched or no_sponsor_hit

    llm_result = None
    if not rules_conclusive or not sponsorship_conclusive:
        try:
            llm_result = _llm_classify(company_name, position_title, job_description)
            signals["llm_judgment"] = llm_result
        except Exception as exc:  # noqa: BLE001 - degrade gracefully, don't crash the request
            signals["llm_error"] = str(exc)
            llm_result = None

    # --- Resolve staffing verdict ---
    if staffing_from_blocklist:
        is_staffing, staffing_conf, staffing_reason = (
            True,
            0.95,
            "Company is on your staffing blocklist.",
        )
    elif staffing_keyword_hit:
        is_staffing, staffing_conf, staffing_reason = (
            True,
            0.75,
            f"JD contains staffing-agency language ('{staffing_keyword_hit}').",
        )
    elif llm_result:
        is_staffing = llm_result["is_staffing"]
        staffing_conf = llm_result["staffing_confidence"]
        staffing_reason = llm_result["staffing_reason"]
    else:
        is_staffing, staffing_conf, staffing_reason = (
            False,
            0.3,
            "No staffing signals found; low-confidence default.",
        )

    # --- Resolve sponsorship verdict ---
    if no_sponsor_hit and not h1b_result.matched:
        sponsorship_status = SponsorshipStatus.citizen_pr_only
        sponsorship_conf = 0.8
        sponsorship_reason = f"JD explicitly restricts sponsorship ('{no_sponsor_hit}')."
    elif h1b_result.matched and not no_sponsor_hit:
        sponsorship_status = SponsorshipStatus.sponsors
        sponsorship_conf = h1b_result.confidence
        sponsorship_reason = (
            f"Company matched H1B filing history in {h1b_result.recent_years}."
        )
    elif h1b_result.matched and no_sponsor_hit:
        # Conflicting signals: company sponsors in general, but this specific
        # posting says otherwise (some roles/locations may be excluded).
        sponsorship_status = SponsorshipStatus.citizen_pr_only
        sponsorship_conf = 0.6
        sponsorship_reason = (
            "Company has H1B history, but this JD explicitly restricts "
            "sponsorship for this specific role."
        )
    elif llm_result:
        sponsorship_status = SponsorshipStatus(llm_result["sponsorship_status"])
        sponsorship_conf = llm_result["sponsorship_confidence"]
        sponsorship_reason = llm_result["sponsorship_reason"]
    else:
        sponsorship_status = SponsorshipStatus.unclear
        sponsorship_conf = 0.3
        sponsorship_reason = "No clear signal found."

    return ScreeningResult(
        is_staffing=is_staffing,
        staffing_confidence=staffing_conf,
        staffing_reason=staffing_reason,
        sponsorship_status=sponsorship_status,
        sponsorship_confidence=sponsorship_conf,
        sponsorship_reason=sponsorship_reason,
        h1b_sponsor_match=h1b_result.matched,
        h1b_match_confidence=h1b_result.confidence,
        h1b_recent_years=h1b_result.recent_years,
        signals=signals,
    )
