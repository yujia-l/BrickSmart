FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-gcp.txt .
RUN pip install --no-cache-dir -r requirements-gcp.txt

COPY . .

EXPOSE 8080

ENV PORT=8080

CMD ["streamlit", "run", "home.py", "--server.port=8080", "--server.address=0.0.0.0", "--server.headless=true"]
