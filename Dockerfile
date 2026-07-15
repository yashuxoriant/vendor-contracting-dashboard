# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Build React frontend
# ─────────────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

# Install dependencies first (cached layer)
COPY frontend/package*.json ./
RUN npm ci --silent

# Copy source and build
COPY frontend/ ./
RUN npm run build

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Python backend + serve built frontend as static files
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS backend

# System deps:
#   gcc + libffi-dev   → cryptography (python-jose, passlib)
#   libxml2-dev + libxslt1-dev → lxml (python-docx)
#   zlib1g-dev         → Pillow / openpyxl image support
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Upgrade pip first to avoid legacy resolver issues, then install deps
COPY backend/requirements-api.txt ./requirements.txt
RUN pip install --upgrade pip --no-cache-dir \
 && pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./

# Copy built frontend into a static/ folder the backend can serve
COPY --from=frontend-build /app/frontend/dist ./static

# Mount point for environment config (injected at runtime via ACR / ACI / AKS)
# Required env vars: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, JWT_SECRET_KEY
# Optional overrides: see backend/config.py for full list

EXPOSE 8000

# Serve with uvicorn; static files are served by the StaticFiles mount below.
# Use --workers 1 in container (scale via replicas, not threads).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
