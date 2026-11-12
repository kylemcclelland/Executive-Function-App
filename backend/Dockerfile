# Optima Pars API: production image (built by Railway from the `backend/` directory).
#
# One process on purpose. The Goodreads import-preview store, the Open Library request pacer and the
# Google access-token cache live in memory, so never run more than one instance or worker until the
# import store moves into the database. Migrations run at start-up; with a single instance and
# additive migrations that is safe and keeps deployment to one step.

# The Divinum Officium engine (Perl, MIT licence), pinned to one upstream commit and checked by SHA-256. It computes the
# traditional (1960) liturgical calendar and the Divine Office; see docs/divine-office.md. To move the pin, change both
# values together (the checksum is of GitHub's tar.gz archive of that commit) and re-run the engine tests.
FROM python:3.12-slim AS divinum-officium
ARG DIVINUM_OFFICIUM_COMMIT=e3e0894e00318a6fc5daae309c845ec5f300837a
ARG DIVINUM_OFFICIUM_SHA256=bd88a529092e7a4d87a922b6cbf2c8d95e43283e6fb390f137b173a88453d874
COPY scripts/fetch_divinum_officium.py /tmp/
RUN python /tmp/fetch_divinum_officium.py "$DIVINUM_OFFICIUM_COMMIT" "$DIVINUM_OFFICIUM_SHA256" /opt/divinum-officium

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

# Perl for the engine. The engine's own code imports only core modules and CGI (CGI, CGI::Cookie, CGI::Carp).
RUN apt-get update \
    && apt-get install -y --no-install-recommends perl libcgi-pm-perl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=divinum-officium /opt/divinum-officium /opt/divinum-officium
ENV DIVINUM_OFFICIUM_PATH=/opt/divinum-officium \
    DIVINUM_OFFICIUM_PERL=perl

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
