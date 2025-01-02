FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get -y upgrade && \
    apt-get install -y --no-install-recommends \
    curl \
    software-properties-common \
    git \
    gpg-agent \
    ffmpeg \
    sox \
    && \
    rm -rf /var/lib/apt/lists/*

RUN add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-dev \
    python3.12-venv \
    && \
    rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /src

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Then, add the rest of the project source code and install it
# Installing separately from its dependencies allows optimal layer caching
ADD . /src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# $WHISPER_INSTALL_INSTRUCTIONS

COPY app app
COPY config config
COPY docker/docker-entrypoint.sh /usr/local/bin/

ENV PYTHONPATH=/src

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["api"]

ARG GIT_COMMIT
ENV GIT_COMMIT=${GIT_COMMIT}
