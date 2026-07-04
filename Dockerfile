FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY pesi /app/pesi
COPY data /app/data
COPY tests /app/tests

RUN python -m pip install --upgrade pip && python -m pip install -e .

EXPOSE 8000

CMD ["uvicorn", "pesi.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
