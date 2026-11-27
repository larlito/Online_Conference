FROM ghcr.io/astral-sh/uv:0.13.9 AS uv
FROM python:3.12-slim

COPY --from=uv /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project
COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src

RUN useradd --uid 10001 --no-create-home appuser
USER appuser
ENV APP_HOST=0.0.0.0 PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec python src/main.py"]
