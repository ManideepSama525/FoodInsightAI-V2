FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app
COPY pyproject.toml README.md ./
COPY backend ./backend
COPY docs ./docs
COPY alembic.ini ./
RUN python -m pip install --upgrade pip && pip install . && pip install --index-url https://download.pytorch.org/whl/cpu torch==2.6.0 "numpy>=1.26,<3.0"
RUN mkdir -p /app/storage/uploads /app/artifacts && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
