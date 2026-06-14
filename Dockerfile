FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/uploads /app/static && \
    python -c "\
import urllib.request; \
urllib.request.urlretrieve('https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui-bundle.js', '/app/static/swagger-ui-bundle.js'); \
urllib.request.urlretrieve('https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui.css', '/app/static/swagger-ui.css'); \
urllib.request.urlretrieve('https://cdn.jsdelivr.net/npm/redoc@2.1.3/bundles/redoc.standalone.js', '/app/static/redoc.standalone.js'); \
print('Static files downloaded.')"
