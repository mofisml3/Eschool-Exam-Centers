FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 ECSA_DATA_DIR=/data
WORKDIR /app

COPY pyproject.toml README.md ./
COPY ecsa ./ecsa
RUN pip install --upgrade pip && pip install ".[ui,postgres]"

COPY docs ./docs
COPY specs ./specs
RUN mkdir -p /data && useradd -m ecsa && chown -R ecsa /data /app
USER ecsa

EXPOSE 8000 8501
# Default: the API. The UI service overrides the command (see render.yaml / docker-compose.yml).
CMD ["sh", "-c", "uvicorn ecsa.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
