FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir ".[dev]"

COPY src/ ./src/
COPY tests/ ./tests/

VOLUME ["/data"]
EXPOSE 8000

CMD ["python", "-m", "src.web.app"]
