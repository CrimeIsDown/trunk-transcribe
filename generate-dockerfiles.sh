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

export WORKER_PACKAGES="git ffmpeg sox"

# Setup Dockerfile.whisper
export WHISPER_INSTALL_INSTRUCTIONS="Install Whisper
ARG DESIRED_CUDA
ARG TARGETPLATFORM
COPY bin/install-whisper.sh /usr/local/bin/install-whisper.sh
RUN install-whisper.sh

ARG WHISPER_MODEL=base.en
ENV WHISPER_MODEL=\${WHISPER_MODEL}
# Pre-download the Whisper model
RUN python3 -c \"import whisper; import os; whisper.load_model(os.getenv('WHISPER_MODEL'))\""

envsubst '$WORKER_PACKAGES $WHISPER_INSTALL_INSTRUCTIONS' < Dockerfile >> Dockerfile.whisper

sed -i 's#CMD \["api"\]#CMD ["worker"]#g' Dockerfile.whisper

# Setup Dockerfile.whispercpp
cat .Dockerfile.whispercpp.template >> Dockerfile.whispercpp
echo >> Dockerfile.whispercpp

export WHISPER_INSTALL_INSTRUCTIONS="Install Whisper.cpp
COPY --from=whispercpp /whisper.cpp/main /usr/local/bin/whisper-cpp
COPY --from=whispercpp /whisper.cpp/models/ggml-*.bin /usr/local/lib/whisper-models/
ENV WHISPERCPP=/usr/local/lib/whisper-models"

envsubst '$WORKER_PACKAGES $WHISPER_INSTALL_INSTRUCTIONS' < Dockerfile >> Dockerfile.whispercpp

sed -i 's#CMD \["api"\]#CMD ["worker"]#g' Dockerfile.whispercpp

echo "Generated Dockerfile.whisper and Dockerfile.whispercpp successfully."
