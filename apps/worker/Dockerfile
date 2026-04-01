FROM python:3.13-slim

WORKDIR /app

COPY apps/worker/pyproject.toml /app/pyproject.toml
COPY apps/worker/app /app/app

RUN pip install --no-cache-dir .

CMD ["python", "-m", "app.main"]
