# The API image. Multi-stage: wheels are built where a compiler exists and
# installed where one does not, so the runtime layer carries no build toolchain
# and nothing that could compile anything at run time.

# --- build ------------------------------------------------------------------
FROM python:3.11-slim AS build

# psycopg needs libpq to build; the runtime only needs the shared library.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# --- runtime ----------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 curl \
 && rm -rf /var/lib/apt/lists/*

# Not root. A compromised web process should not be able to rewrite the code it
# is running, so the app is owned by root and executed by someone else.
RUN useradd --create-home --uid 10001 finmentor

COPY --from=build /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
 && rm -rf /wheels requirements.txt

WORKDIR /app
COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts
COPY alembic.ini ./
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER finmentor
EXPOSE 8000

# The compose healthcheck hits this too, so `depends_on: service_healthy`
# waits for a *working* API rather than a started process.
HEALTHCHECK --interval=15s --timeout=3s --start-period=40s --retries=3 \
  CMD curl -fsS http://localhost:8000/healthz || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
