FROM python:3.14-slim AS base

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_PREFERENCE=only-system

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=/app/uv.lock \
    --mount=type=bind,source=pyproject.toml,target=/app/pyproject.toml \
    uv sync --frozen --no-dev

COPY src /app/src

FROM python:3.14-slim AS final

EXPOSE 8000

ENV PYTHONUNBUFFERED=1
ARG VERSION=0.1.0
ENV APP_VERSION=$VERSION

WORKDIR /app

COPY --from=base /app /app

ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
