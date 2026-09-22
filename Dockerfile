FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN uv sync --frozen --no-dev --no-editable \
    && useradd --create-home appuser
ENV PATH="/app/.venv/bin:$PATH"
USER appuser
EXPOSE 8000 8501
CMD ["uvicorn", "eventtrader.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
