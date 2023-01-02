ARG CUDA_VERSION=11.7
FROM nvidia/cuda:${CUDA_VERSION}.0-base-ubuntu22.04

# Use the closest mirror instead of default mirror
RUN sed -i 's#http://archive.ubuntu.com/ubuntu/#http://mirror.steadfastnet.com/ubuntu/#g' /etc/apt/sources.list

RUN apt-get update && \
    apt-get -y upgrade && \
    apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    git \
    sox \
    ffmpeg \
    && \
    rm -rf /var/lib/apt/lists/*

COPY install-whisper.sh /usr/local/bin/install-whisper.sh
RUN install-whisper.sh

ARG WHISPER_MODEL=tiny.en
ENV WHISPER_MODEL=${WHISPER_MODEL}
RUN python3 -c "import whisper; import os; whisper.load_model(os.getenv('WHISPER_MODEL'))"

WORKDIR /src
COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY app app
COPY config config

COPY docker-entrypoint.sh /usr/local/bin/
ENTRYPOINT ["docker-entrypoint.sh"]

CMD ["worker"]
