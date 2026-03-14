FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install only production dependencies first (layer caching)
COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir ".[server]"

# ── Runtime ──────────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Non-root user for security
RUN groupadd --gid 1000 reagent && \
    useradd --uid 1000 --gid reagent --create-home reagent

WORKDIR /app

# Copy installed packages from build stage
COPY --from=base /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=base /usr/local/bin /usr/local/bin

# Data volume for SQLite database
RUN mkdir -p /data && chown reagent:reagent /data
VOLUME /data

USER reagent

# Server configuration via environment variables
ENV REAGENT_SERVER_HOST=0.0.0.0 \
    REAGENT_SERVER_PORT=8080 \
    REAGENT_SERVER_DB=/data/reagent.db

# REAGENT_API_KEYS — set at runtime (comma-separated), e.g.:
#   docker run -e REAGENT_API_KEYS="rk-abc,rk-xyz" ...

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

ENTRYPOINT ["reagent", "server", "start"]
CMD ["--host", "0.0.0.0", "--port", "8080", "--db", "/data/reagent.db"]
