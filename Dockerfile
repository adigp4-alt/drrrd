FROM python:3.11-slim

WORKDIR /app

# Install dependencies first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p data

EXPOSE 5000

# Single eventlet worker — required for WebSocket (flask-socketio) support
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "main:app", "--bind", "0.0.0.0:5000", "--timeout", "120"]
