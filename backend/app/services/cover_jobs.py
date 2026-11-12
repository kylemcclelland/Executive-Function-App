# ruff: noqa: E501
"""Resumable cover enrichment: the job state machine the worker drives.

The interactive endpoint (`covers.enrich_covers`) already does one polite, cached, idempotent
batch and persists Open Library's cooldown. This module adds the one missing piece: a durable
job row per user, so the next batch happens on the worker's schedule instead of a browser's.

How a job moves:

  running, next_run_at due   -> claim it, run one batch, fold the results back in
    found / cached progress  -> next_run_at = now (eligible again on the next worker pass)
    429 rate limited         -> next_run_at = the persisted cooldown end, plus a little jitter
    503 unavailable          -> bounded exponential backoff with jitter (60 s, 2 m, 4 m ... 1 h)
    network errors           -> the same backoff on a separate counter; after
                                MAX_RETRIES consecutive failing passes the job pauses itself
                                with the reason recorded, instead of retrying forever
    nothing left to do       -> done
  paused                     -> never touched by the worker until resumed

Every batch's completed work (cover URLs, cached answers, counters) is committed before the next
request is made, so a crash or redeploy between batches loses nothing: the job simply resumes
from its own row. The ``claimed_until`` lease makes overlapping worker passes impossible: a pass
only runs a job after atomically claiming it, and a stale claim expires on its own.
"""

import logging
import random
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update

from ..models import CoverEnrichmentJob
from . import covers

logger = logging.getLogger(__name__)

RUNNING, PAUSED, DONE = "running", "paused", "done"
CLAIM_SECONDS = 10 * 60          # generous: one batch is at most ~5 paced requests (~20 s)
BACKOFF_BASE_SECONDS = 60.0      # 503 and network errors: 60 s, 2 m, 4 m ... capped below
BACKOFF_CAP_SECONDS = 60 * 60.0
JITTER = 0.2                     # +/-20%, so retries from several sources never align
MAX_RETRIES = 8                  # consecutive failing passes before the job pauses itself
BATCH_LIMIT = covers.DEFAULT_BATCH


def backoff_seconds(streak: int, rng=random.random) -> float:
    """Bounded exponential backoff with jitter; streak 1 is the first failure."""
    base = min(BACKOFF_BASE_SECONDS * (2 ** max(0, streak - 1)), BACKOFF_CAP_SECONDS)
    return base * (1 - JITTER + 2 * JITTER * rng())


def job_view(job: CoverEnrichmentJob | None, db, now: datetime) -> dict:
    """What the frontend shows: the job row plus what is actually left to do."""
    if job is None:
        return {"exists": False, "status": None, "books_checked": 0, "covers_found": 0,
                "without_cover": 0, "errors": 0, "remaining": None, "next_run_at": None,
                "last_error": None, "last_progress_at": None, "waiting": False}
    remaining = covers.count_missing(db, job.user_id, [UUID(i) for i in job.skip_ids])
    return {
        "exists": True, "status": job.status, "books_checked": job.books_checked,
        "covers_found": job.covers_found, "without_cover": job.without_cover,
        "errors": job.errors, "remaining": remaining, "next_run_at": job.next_run_at,
        "last_error": job.last_error, "last_progress_at": job.last_progress_at,
        "waiting": job.status == RUNNING and job.next_run_at is not None and job.next_run_at > now,
    }


def get_job(db, user_id) -> CoverEnrichmentJob | None:
    return db.scalar(select(CoverEnrichmentJob).where(CoverEnrichmentJob.user_id == user_id))


def start_job(session_factory, user_id) -> None:
    """Create the user's job, or wake a finished/paused one. Counters of a finished job reset;
    a paused one simply resumes where it stopped."""
    now = covers.utcnow()
    with session_factory.begin() as db:
        job = get_job(db, user_id)
        if job is None:
            db.add(CoverEnrichmentJob(user_id=user_id, status=RUNNING, next_run_at=now,
                                      skip_ids=[], updated_at=now))
            return
        if job.status == DONE:
            job.books_checked = job.covers_found = job.without_cover = job.errors = 0
            job.skip_ids = []
        job.status = RUNNING
        job.retry_count = job.unavailable_streak = 0
        job.last_error = None
        job.next_run_at = now
        job.updated_at = now


def set_status(session_factory, user_id, status: str) -> bool:
    now = covers.utcnow()
    with session_factory.begin() as db:
        job = get_job(db, user_id)
        if job is None:
            return False
        job.status = status
        if status == RUNNING:
            job.retry_count = job.unavailable_streak = 0
            job.last_error = None
            job.next_run_at = now
        job.updated_at = now
        return True


def claim_job(session_factory, job_id, now: datetime) -> bool:
    """Atomically take the lease. Exactly one concurrent caller can win this UPDATE."""
    jobs = CoverEnrichmentJob.__table__
    with session_factory.begin() as db:
        won = db.execute(
            update(jobs)
            .where(
                jobs.c.id == job_id, jobs.c.status == RUNNING,
                jobs.c.next_run_at <= now,
                (jobs.c.claimed_until.is_(None)) | (jobs.c.claimed_until < now),
            )
            .values(claimed_until=now + timedelta(seconds=CLAIM_SECONDS), updated_at=now)
        ).rowcount
    return won == 1


def run_one_batch(session_factory, job_id, rng=random.random) -> dict:
    """One claimed batch: call the existing enrichment, then fold its outcome into the job row."""
    with session_factory() as db:
        job = db.get(CoverEnrichmentJob, job_id)
        user_id, skip = job.user_id, [UUID(i) for i in job.skip_ids]
    result = covers.enrich_covers(session_factory, user_id, BATCH_LIMIT, skip)
    now = covers.utcnow()
    with session_factory.begin() as db:
        job = db.get(CoverEnrichmentJob, job_id)
        job.books_checked += result["checked"]
        job.covers_found += len(result["updated"])
        job.without_cover += result["not_found"]
        job.errors += result["errors"]
        job.skip_ids = job.skip_ids + [str(i) for i in result["checked_ids"]]
        made_progress = result["updated"] or result["cached"] or result["not_found"]
        if result["rate_limited"]:
            job.retry_count = 0
            job.unavailable_streak = 0
            job.last_error = "Open Library asked us to wait (rate limited)."
            job.next_run_at = result["blocked_until"] + timedelta(seconds=30 * rng())
        elif result["unavailable"]:
            job.retry_count = 0
            job.unavailable_streak += 1
            job.last_error = "Open Library is temporarily unavailable."
            wait = backoff_seconds(job.unavailable_streak, rng)
            job.next_run_at = max(result["blocked_until"], now + timedelta(seconds=wait))
        elif result["stopped_early"] or (result["errors"] and not made_progress):
            # Network errors, whether they ended the batch or merely wasted it: back off, never
            # hammer the same failing lookup, and give up (pausing, with the reason kept) after
            # MAX_RETRIES consecutive fruitless passes.
            job.retry_count += 1
            job.last_error = "Could not reach Open Library (network errors)."
            if job.retry_count >= MAX_RETRIES:
                job.status = PAUSED
                job.last_error = f"Paused after {MAX_RETRIES} failing attempts (network errors)."
            else:
                job.next_run_at = now + timedelta(seconds=backoff_seconds(job.retry_count, rng))
        elif result["remaining"] == 0 and result["legacy_remaining"] == 0:
            job.status = DONE
            job.retry_count = job.unavailable_streak = 0
            job.last_error = None
            job.next_run_at = None
        else:
            job.retry_count = job.unavailable_streak = 0
            job.last_error = None
            job.next_run_at = now
        if made_progress:
            job.last_progress_at = now
        job.claimed_until = None
        job.updated_at = now
        status, next_run = job.status, job.next_run_at
    logger.info(
        "cover job batch: job=%s checked=%d found=%d status=%s next_run=%s",
        job_id, result["checked"], len(result["updated"]), status,
        next_run.isoformat() if next_run else None,
    )
    return {"status": status, "next_run_at": next_run, **result}


def run_due_jobs(session_factory, batches_per_job: int = 5, rng=random.random) -> dict:
    """One bounded worker pass: for every due job, up to ``batches_per_job`` batches, then exit.

    A pass never waits for a cooldown: when a batch starts one, the job's ``next_run_at`` moves
    into the future and the pass goes on to other jobs (or exits). The next scheduled pass picks
    it up after the cooldown ends — that is the automatic resumption.
    """
    summary = {"jobs_run": 0, "batches": 0, "found": 0}
    now = covers.utcnow()
    with session_factory() as db:
        due = db.scalars(
            select(CoverEnrichmentJob.id).where(
                CoverEnrichmentJob.status == RUNNING, CoverEnrichmentJob.next_run_at <= now,
            )
        ).all()
    for job_id in due:
        if not claim_job(session_factory, job_id, covers.utcnow()):
            continue       # another pass holds it, or it is no longer due
        summary["jobs_run"] += 1
        for batch in range(max(1, batches_per_job)):
            if batch and not claim_job(session_factory, job_id, covers.utcnow()):
                break      # someone else took it between batches
            outcome = run_one_batch(session_factory, job_id, rng)
            summary["batches"] += 1
            summary["found"] += len(outcome["updated"])
            if outcome["status"] != RUNNING or outcome["next_run_at"] > covers.utcnow():
                break      # done, paused, cooling down or backing off: stop politely
    return summary
