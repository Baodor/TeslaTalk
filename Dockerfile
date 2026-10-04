FROM node:24-alpine AS web
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DB_PATH=/data/teslatalk.sqlite FRONTEND_DIR=/app/frontend
WORKDIR /app
COPY backend/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home teslatalk && mkdir /data && chown teslatalk:teslatalk /data
COPY backend/app ./app
COPY --from=web /build/dist ./frontend
USER teslatalk
EXPOSE 8780
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8780", "--workers", "1", "--no-access-log"]
