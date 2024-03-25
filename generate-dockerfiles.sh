#!/bin/bash
set -e

cat > Dockerfile.whisper << EOF
#
# NOTE: THIS DOCKERFILE IS GENERATED VIA "generate-dockerfiles.sh"
#
# PLEASE DO NOT EDIT IT DIRECTLY.
#
EOF
cp Dockerfile.whisper Dockerfile.whispercpp
cp Dockerfile.whisper Dockerfile.fasterwhisper
cp Dockerfile.whisper Dockerfile.insanelyfastwhisper

# Setup Dockerfile.whisper
export WHISPER_INSTALL_INSTRUCTIONS="Install Whisper
ARG DESIRED_CUDA
ARG TARGETPLATFORM
COPY bin/install-whisper.sh /usr/local/bin/install-whisper.sh
RUN install-whisper.sh

ARG WHISPER_MODEL=base.en
ENV WHISPER_MODEL=\${WHISPER_MODEL}
# Pre-download the Whisper model
RUN python3 -c \"import whisper; import os; whisper.load_model(os.getenv('WHISPER_MODEL'))\"
ENV WHISPER_IMPLEMENTATION=whisper"

envsubst '$WHISPER_INSTALL_INSTRUCTIONS' < Dockerfile >> Dockerfile.whisper

sed -i 's#FROM ubuntu:22.04#FROM nvidia/cuda:11.7.1-base-ubuntu22.04#g' Dockerfile.whisper

sed -i 's#CMD \["api"\]#CMD ["worker"]#g' Dockerfile.whisper

# Setup Dockerfile.fasterwhisper
export WHISPER_INSTALL_INSTRUCTIONS="Install Faster Whisper
COPY bin/install-faster-whisper.sh /usr/local/bin/install-whisper.sh
ARG DESIRED_CUDA
RUN install-whisper.sh

ARG WHISPER_MODEL=base.en
ENV WHISPER_MODEL=\${WHISPER_MODEL}
# Pre-download the Whisper model
RUN python3 -c \"from faster_whisper import WhisperModel; import os; WhisperModel(os.getenv('WHISPER_MODEL'))\"
ENV WHISPER_IMPLEMENTATION=faster-whisper"

envsubst '$WHISPER_INSTALL_INSTRUCTIONS' < Dockerfile >> Dockerfile.fasterwhisper

sed -i 's#FROM ubuntu:22.04#FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04#g' Dockerfile.fasterwhisper

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

# Setup Dockerfile.insanelyfastwhisper
export WHISPER_INSTALL_INSTRUCTIONS="Install Insanely-Fast-Whisper
COPY bin/install-insanely-fast-whisper.sh /usr/local/bin/install-whisper.sh
ARG DESIRED_CUDA
RUN install-whisper.sh

ARG WHISPER_MODEL=base.en
ENV WHISPER_MODEL=\${WHISPER_MODEL}
# Pre-download the Whisper model
RUN python3 -c \"from transformers import pipeline; import os; model_id = 'openai/whisper-' + os.getenv('WHISPER_MODEL'); pipeline('automatic-speech-recognition', model=model_id, device='cpu', model_kwargs={'attn_implementation': 'sdpa'})\"
ENV WHISPER_IMPLEMENTATION=insanely-fast-whisper"

envsubst '$WHISPER_INSTALL_INSTRUCTIONS' < Dockerfile >> Dockerfile.insanelyfastwhisper

sed -i 's#FROM ubuntu:22.04#FROM nvidia/cuda:11.7.1-devel-ubuntu22.04#g' Dockerfile.insanelyfastwhisper

sed -i 's#CMD \["api"\]#CMD ["worker"]#g' Dockerfile.insanelyfastwhisper

echo "Generated Dockerfile.whisper, Dockerfile.fasterwhisper, Dockerfile.whispercpp, Dockerfile.insanelyfastwhisper successfully."
