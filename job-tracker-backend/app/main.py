import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import applications, blocklist, job_postings, resumes, stats

load_dotenv()

# In a real production setup you'd use Alembic migrations instead of
# create_all, but this keeps the scaffold runnable out of the box.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Job Application Tracker API",
    description=(
        "Tracks job applications end-to-end: screens postings for staffing "
        "agencies and visa sponsorship before you waste time applying, then "
        "tracks the ones you do apply to through to offer/rejection."
    ),
    version="0.1.0",
)

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(resumes.router)
app.include_router(job_postings.router)
app.include_router(applications.router)
app.include_router(blocklist.router)
app.include_router(stats.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
