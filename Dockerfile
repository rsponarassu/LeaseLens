# syntax=docker/dockerfile:1
#
# LeaseLens in one image: the Vite client is built first, then FastAPI serves it
# from the same process, so the app and the API share one origin - no CORS, no
# second service to keep in sync.
#
# Render passes every service environment variable to the build as a Docker build
# argument, so VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY declared below are
# filled in from the dashboard without extra configuration. All three are public
# values (the publishable key ships in the bundle by design).

# ---- 1. Build the web client -----------------------------------------------
FROM node:22-slim AS web
WORKDIR /web

# Copy the manifests first so `npm ci` is cached until a dependency changes.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./

ARG VITE_SUPABASE_URL=""
ARG VITE_SUPABASE_ANON_KEY=""
ARG VITE_API_BASE_URL=""
ENV VITE_SUPABASE_URL=${VITE_SUPABASE_URL} \
    VITE_SUPABASE_ANON_KEY=${VITE_SUPABASE_ANON_KEY} \
    VITE_API_BASE_URL=${VITE_API_BASE_URL}

# tsc --noEmit runs first, so a type error fails the image instead of shipping.
RUN npm run build

# ---- 2. Runtime ------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    ENVIRONMENT=production \
    SERVE_FRONTEND=true

# Tesseract only matters for scanned leases: without it the parser reports OCR as
# "limited" and text PDFs are unaffected, so this package is a convenience, not a
# requirement.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# app/ holds the rule base and the demonstrable samples; frontend/dist is what
# _mount_frontend serves at "/". Config resolves both relative to /app.
COPY app ./app
COPY frontend/dist ./frontend/dist

# The server never writes to disk, so an unprivileged user costs nothing.
RUN useradd --create-home --uid 1000 leaselens
USER leaselens

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT','8000') + '/api/v1/health', timeout=4)"

# PORT is injected by the platform (Render uses 10000); 8000 keeps local runs
# identical to the README.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
