FROM ubuntu:22.04

RUN apt-get update && \
    apt-get -y upgrade && \
    apt-get install -y --no-install-recommends \
    curl \
    python3 \
    python3-pip \
    python3-dev \
    git \
    ffmpeg \
    sox \
    && \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install poetry>=1.3.2

# $WHISPER_INSTALL_INSTRUCTIONS

WORKDIR /src
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false && \
    poetry install --without dev --no-root --no-interaction --no-ansi

COPY app app
COPY config config
COPY bin bin
COPY docker/docker-entrypoint.sh /usr/local/bin/

ENV PYTHONPATH=/src

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["api"]

ARG GIT_COMMIT
ENV GIT_COMMIT=${GIT_COMMIT}
