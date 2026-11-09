FROM ghcr.io/astral-sh/uv:0.13.7 AS uv

FROM python:3.13-slim-bookworm AS dependencies

COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-cache

FROM python:3.13-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PATH="/app/.venv/bin:$PATH"

RUN groupadd --system orqbit \
    && useradd --system --gid orqbit --no-create-home orqbit
WORKDIR /app

COPY --from=dependencies /app/.venv /app/.venv
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./

USER orqbit
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
