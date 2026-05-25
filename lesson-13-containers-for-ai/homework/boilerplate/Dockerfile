# syntax=docker/dockerfile:1.7

# ---------- Stage 1: builder ----------
# Installs deps into an isolated venv. Build toolchain stays here and never
# reaches the final image.
FROM python:3.13-slim-trixie AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Refresh system packages so security patches land in the venv stage too
# (mainly matters if any pip wheel pulls native deps from apt).
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

# requirements.txt is copied first so this layer caches across code changes.
COPY app/requirements.txt ./requirements.txt

RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip setuptools wheel \
 && /opt/venv/bin/pip install -r requirements.txt

# ---------- Stage 2: runtime ----------
FROM python:3.13-slim-trixie AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Pull security patches into the runtime image, then strip apt caches.
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

# Non-root user.
RUN groupadd --system app && useradd --system --gid app --home /app app

WORKDIR /app

# Copy the prepared venv from the builder.
COPY --from=builder /opt/venv /opt/venv

# Copy only what the app needs at runtime.
COPY --chown=app:app app/ ./app/
COPY --chown=app:app data/ ./data/

USER app

EXPOSE 8000

# urllib is in stdlib, so no extra package needed for the probe.
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request, json, sys; \
r = urllib.request.urlopen('http://localhost:8000/health', timeout=2); \
sys.exit(0 if json.loads(r.read())['status'] == 'ok' else 1)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
