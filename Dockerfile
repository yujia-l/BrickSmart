FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir --retries 5 --timeout 120 -r requirements.txt

COPY . .

EXPOSE 8080

ENV PORT=8080

CMD ["python", "cloudrun_start.py"]
