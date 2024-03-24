#!/bin/bash

set -eou pipefail

pip3 install -U pip setuptools wheel

if [ -z "${DESIRED_CUDA:-}" ]; then
    if command -v nvidia-smi >/dev/null 2>&1; then
        # We could try to read the nvidia-smi output but there aren't many compatible PyTorch versions anyway
        DESIRED_CUDA="cu117"
    else
        echo "Could not find nvidia-smi, using CPU-only PyTorch" >&2
        DESIRED_CUDA="cpu"
    fi
fi

if [[ "$DESIRED_CUDA" != "cu117" ]]; then
    EXTRA_INDEX_URL="--extra-index-url https://download.pytorch.org/whl/$DESIRED_CUDA"
else
    EXTRA_INDEX_URL=""
fi

pip3 install --upgrade torch torchvision torchaudio transformers optimum accelerate
if [[ "$DESIRED_CUDA" != "cpu" ]]; then
    pip3 install packaging ninja
    pip3 install flash-attn --no-build-isolation
fi
