FROM ubuntu:24.04

RUN apt-get update && \
    apt-get -y upgrade && \
    apt-get install -y --no-install-recommends \
    curl \
    python3 \
    python3-pip \
    python3-dev \
    pipx \
    git \
    ffmpeg \
    sox \
    && \
    rm -rf /var/lib/apt/lists/*

RUN pipx install poetry

ENV PATH="/root/.local/bin:${PATH}"

# $WHISPER_INSTALL_INSTRUCTIONS

WORKDIR /src
COPY pyproject.toml poetry.lock ./
RUN poetry install --without dev --no-root --no-interaction --no-ansi

COPY app app
COPY config config
COPY docker/docker-entrypoint.sh /usr/local/bin/

ENV PYTHONPATH=/src

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["api"]

ARG GIT_COMMIT
ENV GIT_COMMIT=${GIT_COMMIT}
