#!/bin/bash

set -eou pipefail

if [ -z "${CUDA_VERSION:-}" ]; then
    if command -v nvidia-smi >/dev/null 2>&1; then
        # Read the cuda version from nvidia-smi
        CUDA_VERSION="12.1.0"
    else
        echo "Could not find nvidia-smi, using CPU-only PyTorch" >&2
        CUDA_VERSION="cpu"
    fi
fi

if [ "$CUDA_VERSION" = "cpu" ]; then
    EXTRA_INDEX_URL="--extra-index-url https://download.pytorch.org/whl/cpu"
else
    EXTRA_INDEX_URL="--extra-index-url https://download.pytorch.org/whl/cu$(echo $CUDA_VERSION | cut -d. -f1-2 | tr -d .)"
fi

poetry run pip3 install --use-pep517 $EXTRA_INDEX_URL --no-cache-dir torch torchaudio

poetry run pip3 install --use-pep517 $EXTRA_INDEX_URL --no-cache-dir $1
