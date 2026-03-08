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

# Use gunicorn for production
CMD ["gunicorn", "main:app", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120"]
