FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    git \
    && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /src

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

COPY pyproject.toml pyproject.toml
COPY backend/pyproject.toml backend/pyproject.toml
COPY uv.lock uv.lock

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --directory backend --no-install-project --no-dev

COPY backend/alembic.ini backend/alembic.ini
COPY backend/app backend/app
COPY config config
COPY docker/docker-entrypoint.sh docker/celery-healthcheck.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh /usr/local/bin/celery-healthcheck.sh

ENV PYTHONPATH=/src/backend

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["api"]

ARG GIT_COMMIT
ENV GIT_COMMIT=${GIT_COMMIT}
