FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN useradd --create-home --uid 10001 zvonko

COPY --chown=zvonko:zvonko pyproject.toml README.md ./
COPY --chown=zvonko:zvonko app ./app
COPY --chown=zvonko:zvonko evals ./evals
COPY --chown=zvonko:zvonko scripts ./scripts
COPY --chown=zvonko:zvonko alembic.ini ./
RUN pip install --no-cache-dir .

USER zvonko
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
