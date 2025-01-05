#!/bin/bash
set -e

cd "$(dirname "$0")"

cat > Dockerfile.whisper << EOF
#
# NOTE: THIS DOCKERFILE IS GENERATED VIA "generate-dockerfiles.sh"
#
# PLEASE DO NOT EDIT IT DIRECTLY.
#
EOF
cp Dockerfile.whisper Dockerfile.fasterwhisper
cp Dockerfile.whisper Dockerfile.whispers2t
cp Dockerfile.whisper Dockerfile.whispercpp

echo "ARG CUDA_VERSION=12.1.0" >> Dockerfile.whisper
echo "ARG CUDA_VERSION=12.3.2" >> Dockerfile.fasterwhisper
echo "ARG CUDA_VERSION=12.1.0" >> Dockerfile.whispers2t

# Setup Dockerfile.whisper
export WHISPER_IMPLEMENTATION_GROUP="--group whisper"
export WHISPER_INSTALL_INSTRUCTIONS="Setup Whisper
ARG WHISPER_MODEL=base.en
ENV WHISPER_MODEL=\${WHISPER_MODEL}
# Pre-download the Whisper model
RUN uv run python -c \"import whisper; import os; whisper.load_model(os.getenv('WHISPER_MODEL'))\"
ENV WHISPER_IMPLEMENTATION=whisper"

envsubst '$WHISPER_IMPLEMENTATION_GROUP $WHISPER_INSTALL_INSTRUCTIONS' < Dockerfile >> Dockerfile.whisper

sed -i 's#FROM ubuntu:22.04#FROM nvidia/cuda:${CUDA_VERSION}-base-ubuntu22.04#g' Dockerfile.whisper

sed -i 's#CMD \["api"\]#CMD ["worker"]#g' Dockerfile.whisper

# Setup Dockerfile.fasterwhisper
export WHISPER_IMPLEMENTATION_GROUP="--group faster-whisper"
export WHISPER_INSTALL_INSTRUCTIONS="Setup Faster Whisper
ARG WHISPER_MODEL=base.en
ENV WHISPER_MODEL=\${WHISPER_MODEL}
# Pre-download the Whisper model
RUN uv run python -c \"import os; from faster_whisper.utils import download_model; download_model(os.getenv('WHISPER_MODEL'))\"
ENV WHISPER_IMPLEMENTATION=faster-whisper"

envsubst '$WHISPER_IMPLEMENTATION_GROUP $WHISPER_INSTALL_INSTRUCTIONS' < Dockerfile >> Dockerfile.fasterwhisper

sed -i 's#FROM ubuntu:22.04#FROM nvidia/cuda:${CUDA_VERSION}-cudnn9-runtime-ubuntu22.04#g' Dockerfile.fasterwhisper

sed -i 's#CMD \["api"\]#CMD ["worker"]#g' Dockerfile.fasterwhisper

# Setup Dockerfile.whispers2t
export WHISPER_IMPLEMENTATION_GROUP="--group whispers2t"
export WHISPER_INSTALL_INSTRUCTIONS="Setup WhisperS2T
ARG WHISPER_MODEL=base.en
ENV WHISPER_MODEL=\${WHISPER_MODEL}
# Pre-download the Whisper model
RUN uv run python -c \"import os; from whisper_s2t.backends.ctranslate2.hf_utils import download_model; download_model(os.getenv('WHISPER_MODEL'))\"
ENV WHISPER_IMPLEMENTATION=whispers2t
ENV TQDM_DISABLE=1"

envsubst '$WHISPER_IMPLEMENTATION_GROUP $WHISPER_INSTALL_INSTRUCTIONS' < Dockerfile >> Dockerfile.whispers2t

sed -i 's#FROM ubuntu:22.04#FROM nvidia/cuda:${CUDA_VERSION}-cudnn8-runtime-ubuntu22.04#g' Dockerfile.whispers2t

sed -i 's#CMD \["api"\]#CMD ["worker"]#g' Dockerfile.whispers2t

# Setup Dockerfile.whispercpp
cat .Dockerfile.whispercpp.template >> Dockerfile.whispercpp
echo >> Dockerfile.whispercpp

export WHISPER_INSTALL_INSTRUCTIONS="Install Whisper.cpp
COPY --from=whispercpp /whisper.cpp/main /usr/local/bin/whisper-cpp
COPY --from=whispercpp /whisper.cpp/models/ggml-*.bin /usr/local/lib/whisper-models/
ENV WHISPER_IMPLEMENTATION=whisper.cpp
ARG WHISPER_MODEL=base.en
ENV WHISPER_MODEL=\${WHISPER_MODEL}
ENV WHISPERCPP_MODEL_DIR=/usr/local/lib/whisper-models"

envsubst '$WHISPER_INSTALL_INSTRUCTIONS' < Dockerfile >> Dockerfile.whispercpp

sed -i 's#CMD \["api"\]#CMD ["worker"]#g' Dockerfile.whispercpp

echo "Generated Dockerfile.whisper, Dockerfile.fasterwhisper, Dockerfile.whispers2t, and Dockerfile.whispercpp successfully."
