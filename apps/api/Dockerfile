FROM python:3.13-slim

WORKDIR /app

COPY apps/api/pyproject.toml /app/pyproject.toml
COPY apps/api/alembic.ini /app/alembic.ini
COPY apps/api/alembic /app/alembic
COPY apps/api/app /app/app
COPY apps/api/scripts /app/scripts

RUN pip install --no-cache-dir .

EXPOSE 3001

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3001"]
