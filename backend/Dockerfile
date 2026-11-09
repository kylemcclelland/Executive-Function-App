# Optima Pars API: production image (built by Railway from the `backend/` directory).
#
# One process on purpose. The Goodreads import-preview store, the Open Library request pacer and the
# Google access-token cache live in memory, so never run more than one instance or worker until the
# import store moves into the database. Migrations run at start-up; with a single instance and
# additive migrations that is safe and keeps deployment to one step.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

# Dependencies first (cached until the lock file changes). The lock also lists test tooling,
# which the running service does not need.
COPY requirements.lock ./
RUN grep -viE '^(pytest|ruff|pluggy|iniconfig|pygments)==' requirements.lock > requirements.runtime.txt \
    && pip install -r requirements.runtime.txt \
    && rm requirements.runtime.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts

# Never run as root.
RUN useradd --system --uid 10001 --no-create-home appuser
USER appuser

EXPOSE 8000
# Railway injects $PORT. `exec` hands the process to uvicorn so it receives SIGTERM on redeploys.
CMD ["sh", "-c", "python -m alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-server-header"]
