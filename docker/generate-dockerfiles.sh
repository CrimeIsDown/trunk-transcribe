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
cp Dockerfile.whisper Dockerfile.whispercpp
cp Dockerfile.whisper Dockerfile.fasterwhisper
cp Dockerfile.whisper Dockerfile.whispers2t

# Setup Dockerfile.whisper
export WHISPER_INSTALL_INSTRUCTIONS="Install Whisper
ARG DESIRED_CUDA
ARG TARGETPLATFORM
COPY docker/install-whisper.sh /usr/local/bin/install-whisper.sh
RUN install-whisper.sh

ARG WHISPER_MODEL=base.en
ENV WHISPER_MODEL=\${WHISPER_MODEL}
# Pre-download the Whisper model
RUN python3 -c \"import whisper; import os; whisper.load_model(os.getenv('WHISPER_MODEL'))\"
ENV WHISPER_IMPLEMENTATION=whisper"

envsubst '$WHISPER_INSTALL_INSTRUCTIONS' < Dockerfile >> Dockerfile.whisper

sed -i 's#FROM ubuntu:24.04#FROM nvidia/cuda:12.6.0-base-ubuntu24.04#g' Dockerfile.whisper

sed -i 's#CMD \["api"\]#CMD ["worker"]#g' Dockerfile.whisper

# Setup Dockerfile.fasterwhisper
export WHISPER_INSTALL_INSTRUCTIONS="Install Faster Whisper
COPY docker/install-faster-whisper.sh /usr/local/bin/install-whisper.sh
ARG DESIRED_CUDA
RUN install-whisper.sh

ARG WHISPER_MODEL=base.en
ENV WHISPER_MODEL=\${WHISPER_MODEL}
# Pre-download the Whisper model
RUN python3 -c \"import os; from faster_whisper.utils import download_model; download_model(os.getenv('WHISPER_MODEL'))\"
ENV WHISPER_IMPLEMENTATION=faster-whisper"

envsubst '$WHISPER_INSTALL_INSTRUCTIONS' < Dockerfile >> Dockerfile.fasterwhisper

sed -i 's#FROM ubuntu:24.04#FROM nvidia/cuda:12.6.0-cudnn8-runtime-ubuntu24.04#g' Dockerfile.fasterwhisper

sed -i 's#CMD \["api"\]#CMD ["worker"]#g' Dockerfile.fasterwhisper

# Setup Dockerfile.whispercpp
cat .Dockerfile.whispercpp.template >> Dockerfile.whispercpp
echo >> Dockerfile.whispercpp

export WHISPER_INSTALL_INSTRUCTIONS="Install Whisper.cpp
COPY --from=whispercpp /whisper.cpp/main /usr/local/bin/whisper-cpp
COPY --from=whispercpp /whisper.cpp/models/ggml-*.bin /usr/local/lib/whisper-models/
ENV WHISPER_IMPLEMENTATION=whisper.cpp
ENV WHISPERCPP_MODEL_DIR=/usr/local/lib/whisper-models"

envsubst '$WHISPER_INSTALL_INSTRUCTIONS' < Dockerfile >> Dockerfile.whispercpp

sed -i 's#CMD \["api"\]#CMD ["worker"]#g' Dockerfile.whispercpp

# Setup Dockerfile.whispers2t
export WHISPER_INSTALL_INSTRUCTIONS="Install WhisperS2T
COPY docker/install-whispers2t.sh /usr/local/bin/install-whisper.sh
ARG DESIRED_CUDA
RUN install-whisper.sh

ARG WHISPER_MODEL=base.en
ENV WHISPER_MODEL=\${WHISPER_MODEL}
# Pre-download the Whisper model
RUN python3 -c \"import os; from whisper_s2t.backends.ctranslate2.hf_utils import download_model; download_model(os.getenv('WHISPER_MODEL'))\"
ENV WHISPER_IMPLEMENTATION=whispers2t
ENV TQDM_DISABLE=1"

envsubst '$WHISPER_INSTALL_INSTRUCTIONS' < Dockerfile >> Dockerfile.whispers2t

sed -i 's#FROM ubuntu:24.04#FROM nvidia/cuda:12.6.0-cudnn8-runtime-ubuntu24.04#g' Dockerfile.whispers2t

sed -i 's#CMD \["api"\]#CMD ["worker"]#g' Dockerfile.whispers2t

echo "Generated Dockerfile.whisper, Dockerfile.fasterwhisper, Dockerfile.whispercpp, Dockerfile.whispers2t successfully."
