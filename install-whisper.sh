#!/bin/bash

CUDA_VERSION=${CUDA_VERSION:-11.7.0}

PYTORCH_URL="https://download.pytorch.org/whl/cu$(echo $CUDA_VERSION | tr -d '.0')"

pip3 install \
    --extra-index-url $PYTORCH_URL \
    git+https://github.com/openai/whisper.git
