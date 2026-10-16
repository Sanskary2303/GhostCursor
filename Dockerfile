# Ghost Cursor Multi-Stage Dockerfile
# Targets: api (Orchestrator Service) and demo (ShopHive Demo Storefront)

# ============================================================================
# Stage 1: Python Wheel Builder
# ============================================================================
FROM python:3.12-slim AS py-builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY services/orchestrator/requirements.txt ./api-requirements.txt
COPY demo/shophive/backend/requirements.txt ./demo-requirements.txt
COPY packages/sdk-server-python ./packages/sdk-server-python

RUN pip install --no-cache-dir wheel && \
    pip wheel --no-cache-dir --wheel-dir /wheels -r api-requirements.txt && \
    pip wheel --no-cache-dir --wheel-dir /wheels -r demo-requirements.txt ./packages/sdk-server-python

# ============================================================================
# Stage 2: Orchestrator API Target
# ============================================================================
FROM python:3.12-slim AS api

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY --from=py-builder /wheels /wheels
COPY services/orchestrator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt && \
    rm -rf /wheels

COPY services/orchestrator/app /app/app
COPY services/orchestrator/migrations /app/migrations

RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

# ============================================================================
# Stage 3: Node Frontend Builder
# ============================================================================
FROM node:20-slim AS node-builder

WORKDIR /build

COPY package.json package-lock.json tsconfig.json ./
COPY packages/ packages/
COPY demo/shophive/frontend/ demo/shophive/frontend/

RUN npm ci
RUN npm run build --workspace=packages/sdk-frontend
RUN npm run build --workspace=packages/sdk-react
ARG VITE_E2E_HOOKS=0
ENV VITE_E2E_HOOKS=${VITE_E2E_HOOKS}
RUN npm run build --workspace=demo/shophive/frontend

# ============================================================================
# Stage 4: ShopHive Demo Target
# ============================================================================
FROM python:3.12-slim AS demo

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/demo/shophive/backend

WORKDIR /app/demo/shophive/backend

COPY --from=py-builder /wheels /wheels
COPY demo/shophive/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt ghost-cursor && \
    rm -rf /wheels

COPY demo/shophive/backend /app/demo/shophive/backend
COPY --from=node-builder /build/demo/shophive/frontend/dist /app/demo/shophive/frontend/dist

RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/health')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8081"]

