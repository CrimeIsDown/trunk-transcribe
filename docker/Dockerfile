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
    python3.12-distutils \
    && \
    rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | python3.12 -

ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /src
COPY pyproject.toml poetry.lock ./
RUN poetry env use python3.12 && \
    poetry install --without dev --no-root --no-interaction --no-ansi

# $WHISPER_INSTALL_INSTRUCTIONS

COPY app app
COPY config config
COPY docker/docker-entrypoint.sh /usr/local/bin/

ENV PYTHONPATH=/src

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["api"]

ARG GIT_COMMIT
ENV GIT_COMMIT=${GIT_COMMIT}
