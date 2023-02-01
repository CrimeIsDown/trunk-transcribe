FROM ubuntu:22.04

RUN apt-get update && \
    apt-get -y upgrade && \
    apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    $WORKER_PACKAGES \
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
COPY bin/*.py ./
COPY bin/*.sh /usr/local/bin/

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["api"]

ARG GIT_COMMIT
ENV GIT_COMMIT=${GIT_COMMIT}
