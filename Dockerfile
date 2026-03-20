FROM python:3.11-slim

WORKDIR /app

# Install rsync for atomic snapshots
RUN apt-get update && apt-get install -y rsync curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Create required directories
RUN mkdir -p /opt/resonant/runtime \
    /opt/resonant/core \
    /opt/resonant/snapshots \
    /opt/resonant/state/locks \
    /opt/resonant/logs \
    /opt/resonant/agent

EXPOSE 8093

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8093/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8093"]
