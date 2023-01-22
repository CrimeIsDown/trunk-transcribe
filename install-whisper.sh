#!/bin/bash

set -eou pipefail

WHISPER_PACKAGE=${WHISPER_PACKAGE:-git+https://github.com/openai/whisper.git}

DESIRED_CUDA=${DESIRED_CUDA:-cu117}
PYTORCH_URL="https://download.pytorch.org/whl/$DESIRED_CUDA"
TARGETPLATFORM=${TARGETPLATFORM:-linux/amd64}

if [ "$TARGETPLATFORM" = "linux/amd64" ]; then
    pip3 install --extra-index-url $PYTORCH_URL $WHISPER_PACKAGE
elif [ "$TARGETPLATFORM" = "linux/arm64" ]; then
    pip3 install $WHISPER_PACKAGE
else
    echo "Unsupported platform: $TARGETPLATFORM" >&2
    exit 1
fi
