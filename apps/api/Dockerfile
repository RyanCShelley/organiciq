FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x scripts/start-api.sh scripts/start-worker.sh scripts/start.sh

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV SERVICE_ROLE=api

EXPOSE 8000

# Default = API. Worker service sets SERVICE_ROLE=worker (same image).
CMD ["scripts/start.sh"]
