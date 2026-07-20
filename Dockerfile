FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[postgres]"

COPY . .

EXPOSE 8000
CMD ["gunicorn", "wsgi:app", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
