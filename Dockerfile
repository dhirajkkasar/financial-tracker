# ── Stage 1: Build frontend static files ──────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./

# NEXT_PUBLIC_API_URL is a relative path so the browser calls the same origin.
# Override at build time if needed: --build-arg NEXT_PUBLIC_API_URL=/api
ARG NEXT_PUBLIC_API_URL=/api
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build
# Output: /frontend/out/


# ── Stage 2: Install Python dependencies ──────────────────────────────────────
FROM python:3.11-slim AS python-builder

WORKDIR /build

RUN pip install --no-cache-dir uv

COPY backend/pyproject.toml backend/uv.lock ./

# Export locked deps to a requirements file, then install into /install
# (pip installs to a fixed prefix so scripts don't embed the builder path)
RUN uv export --no-dev --no-emit-project -o requirements.txt && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 3: Runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder — paths are /usr/local-relative so no shebang issues
COPY --from=python-builder /install /usr/local

# Copy backend application code
COPY backend/ ./

# Copy compiled frontend static files into the location main.py looks for
COPY --from=frontend-builder /frontend/out ./frontend_static

# Cloud Run injects PORT (default 8080). Uvicorn binds to 0.0.0.0 so the
# container is reachable. Migrations are run separately via Cloud Run jobs
# or the alembic upgrade head command before first deploy.
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
