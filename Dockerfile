FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY utopia.py .
COPY templates/ templates/

RUN mkdir -p data

EXPOSE 5000

CMD ["python", "utopia.py"]
