FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY alembic.ini ./
COPY alembic ./alembic
RUN useradd --create-home app
USER app
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn signalloop.api.app:app --host 0.0.0.0 --port 8000"]

FROM base AS test
USER root
RUN pip install --no-cache-dir '.[dev]'
COPY tests ./tests
USER app
CMD ["pytest", "-p", "no:cacheprovider", "-q"]
