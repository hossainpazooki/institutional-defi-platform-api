# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir ".[all]"

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -g 1000 app && useradd -u 1000 -g app -s /bin/sh app

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY src/ src/
COPY data/ data/
COPY alembic/ alembic/
COPY alembic.ini .
COPY docker-entrypoint.sh .

RUN chmod +x docker-entrypoint.sh

# Environment for PyTorch workaround and non-root operation
ENV HOME=/tmp \
    USER=app \
    TORCHINDUCTOR_CACHE_DIR=/tmp/torch-cache

EXPOSE 8000

USER 1000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["api"]
