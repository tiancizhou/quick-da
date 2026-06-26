FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app/backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/opencode-worker/package*.json ./opencode-worker/
RUN cd opencode-worker && npm ci --omit=dev

COPY backend/ ./
COPY --from=frontend-build /app/backend/static ./static

EXPOSE 8000

CMD ["sh", "-c", "python prepare_database.py && uvicorn main:app --host 0.0.0.0 --port ${SERVER_PORT:-8000}"]
