# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Keep Python from writing .pyc files and buffering logs behind the container.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000 \
    DATA_DIR=/data

WORKDIR /app

# Dependencies first so the layer caches across source-only changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# /data holds the SQLite database and CSV snapshots. Mount a volume over it
# (`docker run -v tracker-data:/data`) or the forecast ledger's accuracy
# history is lost when the container is replaced. Setting DATABASE_URL to a
# Postgres instance makes the volume unnecessary.
RUN mkdir -p /data && \
    useradd --create-home --uid 10001 appuser && \
    chown -R appuser /app /data
VOLUME ["/data"]
USER appuser

EXPOSE 5000

# One worker: the app starts an APScheduler thread at boot, and a second worker
# would run a duplicate scheduler (double price fetches, double forecast
# grading). Concurrency comes from threads instead. The long timeout is
# deliberate — a catalyst-overlay market scan runs web research through Claude
# and can exceed gunicorn's 30s default.
CMD ["sh", "-c", "gunicorn main:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 300 --access-logfile - --error-logfile -"]
