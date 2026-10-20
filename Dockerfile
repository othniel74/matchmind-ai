# Single-container public demo: the backend serves the API, WebSockets and the built frontend.
# Synthetic data only: research datasets are excluded from both stages (see .dockerignore and
# the frontend build's exclude-research-data step).

FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    MATCHMIND_ENV=demo \
    MATCHMIND_STATIC_DIR=/app/static \
    MATCHMIND_FOUNDATION_DB=/tmp/matchmind/foundation.sqlite3
WORKDIR /app
COPY backend/requirements*.txt ./
RUN pip install --no-cache-dir -r requirements-agents.txt
COPY backend/app ./app
COPY --from=frontend /frontend/dist ./static
RUN useradd --create-home matchmind && mkdir -p /tmp/matchmind && chown matchmind /tmp/matchmind
USER matchmind
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
