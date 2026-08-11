# Job Application Tracker — Backend

A job application tracker with a twist: before you spend time applying,
postings get screened for two common time-wasters —

1. **Staffing/agency postings** — third-party recruiters reposting a client's
   job, often with duplicate/competing candidates and slower feedback loops.
2. **No visa sponsorship** — postings that won't sponsor H1B, filtered out
   using a mix of JD text signals *and* real DOL H1B filing history.

Only postings you decide to pursue become tracked `applications`, which then
flow through a status pipeline (applied → OA → interview → offer/rejected)
with full history for later analysis (e.g. "which resume version actually
gets interviews").

## Why this exists

Built this because I was burning time applying to postings that turned out to
be staffing reposts, or explicitly required citizenship/a green card. Wanted
a tool that filters those out *before* I invest time tailoring a resume and
cover letter, and that gives me real data on what's working.

## Stack

- **FastAPI** + **SQLAlchemy** + **PostgreSQL**
- **Anthropic Claude API** for JD classification (used as a fallback, not
  the primary signal — see below)
- **DOL H1B disclosure data** for factual sponsorship history
- `rapidfuzz` for fuzzy company-name matching against H1B records

## Screening design

Rather than sending every posting to an LLM and trusting the output, both
staffing detection and sponsorship detection use layered signals, cheapest
and most reliable first:

| Dimension | Signal 1 (fast/free) | Signal 2 (fast/free) | Signal 3 (fallback) |
|---|---|---|---|
| Staffing | Company on your blocklist | JD keyword heuristics ("our client", "C2C", "W2 contract") | LLM classification |
| Sponsorship | DOL H1B filing history (factual) | JD keyword heuristics ("no sponsorship", "US citizens only") | LLM classification |

Both dimensions are resolved in a single LLM call when needed, to keep
cost/latency down. See `app/services/ai_classifier.py`.

## Project structure

```
app/
├── main.py                  # FastAPI app, router registration
├── database.py               # SQLAlchemy engine/session
├── models.py                  # ORM models
├── schemas.py                  # Pydantic request/response models
├── routers/
│   ├── resumes.py
│   ├── job_postings.py         # includes /analyze screening endpoint
│   ├── applications.py
│   ├── blocklist.py
│   └── stats.py                 # dashboard aggregation endpoints
├── services/
│   ├── ai_classifier.py         # layered staffing/sponsorship screening
│   └── h1b_matcher.py            # fuzzy company matching against H1B data
└── data/
    └── import_h1b.py             # one-off script to load DOL disclosure data
```

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# fill in DATABASE_URL and ANTHROPIC_API_KEY

# make sure Postgres is running and the database in DATABASE_URL exists

uvicorn app.main:app --reload
```

API docs available at `http://localhost:8000/docs` (Swagger UI, auto-generated
by FastAPI).

### Loading H1B data

Download a fiscal year's LCA disclosure file from the
[DOL Performance Data page](https://www.dol.gov/agencies/eta/foreign-labor/performance),
then:

```bash
python -m app.data.import_h1b --file LCA_Disclosure_Data_FY2025.xlsx --year 2025
```

## Development process

This project was built collaboratively with Claude: I designed the data
model and screening logic based on my own job-search pain points, then
iterated with AI assistance on the FastAPI scaffolding, the H1B fuzzy-matching
approach, and the layered signal-resolution logic. Decisions like "H1B data
should override the LLM when they conflict" and "don't auto-blocklist a
company without user confirmation" were deliberate product calls, not
AI defaults — the AI helped implement them faster, not decide what to build.

## Known limitations / next steps

- `import_h1b.py` does a full aggregation in pandas — fine for a few hundred
  thousand rows, but a production version would push aggregation into SQL or
  pre-build a distinct-company lookup table.
- Company fuzzy-matching uses simple normalization + Levenshtein-style
  scoring; parent/subsidiary relationships (e.g. a JD posted under a
  subsidiary name) aren't resolved.
- No auth yet — this is currently single-user by design (it's a personal
  tool), but a real deployment would need user accounts.
