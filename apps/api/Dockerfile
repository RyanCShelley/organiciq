FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The keyword matcher's model, baked in rather than downloaded on first use.
# Railway's filesystem is ephemeral, so without this the first person to
# press "Suggest pages" after every deploy waits on an 87 MB download.
ENV FASTEMBED_CACHE_PATH=/opt/fastembed
COPY app/services/text_embedding.py /tmp/text_embedding.py
RUN python /tmp/text_embedding.py && rm /tmp/text_embedding.py

COPY . .

RUN chmod +x scripts/start-api.sh scripts/start-worker.sh scripts/start.sh

# Not root. The API and the embedded worker share this container, and the
# worker holds the database URL and every integration key, so anything that
# gets code execution through it — a crawler SSRF, a parser bug — should not
# also own the filesystem. Nothing here writes outside /tmp, except the model
# loader, which takes lock files in its cache — hence /opt/fastembed below.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && chown -R app:app /app /opt/fastembed
USER app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV SERVICE_ROLE=api

EXPOSE 8000

# Default = API. Worker service sets SERVICE_ROLE=worker (same image).
CMD ["scripts/start.sh"]
