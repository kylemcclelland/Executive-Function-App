# ruff: noqa: E501
"""Scheduled cover-enrichment worker: one bounded pass, suitable for a Railway cron job.

Run as ``python -m app.jobs.enrich_book_covers`` — independent of the web process (no FastAPI, no
Uvicorn, no resident loop). Each invocation finds the cover-enrichment jobs that are due (status
``running`` and ``next_run_at`` in the past), claims each with a bounded lease so overlapping
invocations are impossible, runs a few small batches through the same polite Open Library client
the interactive endpoint uses (paced, cached, cooldown-honouring), persists the progress, and
exits. A job whose batch hits a 429 or 503 is rescheduled for after the cooldown or backoff and
is simply picked up by a later invocation: automatic resumption needs no browser and no click.

Pacing: one pass makes at most ``COVER_WORKER_BATCHES`` × 5 requests, each 4 s apart (the
service's global pacer), so a pass of the default 5 batches spends at most ~100 s and stays far
inside Open Library's 100-requests-per-5-minutes cap even with a 5-minute cron cadence.
"""

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.config import Settings  # noqa: E402
from app.db import make_engine, make_session_factory  # noqa: E402
from app.services.cover_jobs import run_due_jobs  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = Settings()  # the same environment-driven configuration as the API: no hardcoded URLs
    batches = int(os.environ.get("COVER_WORKER_BATCHES", "5"))
    engine = make_engine(
        settings.database_url,
        settings.postgres_password.get_secret_value() if settings.postgres_password else None,
    )
    try:
        summary = run_due_jobs(make_session_factory(engine), batches_per_job=batches)
    finally:
        engine.dispose()
    print(f"cover worker: jobs={summary['jobs_run']} batches={summary['batches']} covers_found={summary['found']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
