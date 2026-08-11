FROM python:3.10.19-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN useradd --create-home --uid 10001 fairhire

COPY pyproject.toml README.md ./
COPY backend ./backend
COPY ml_service ./ml_service
COPY configs ./configs

RUN python -m pip install --upgrade pip \
    && python -m pip install .

USER fairhire
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
