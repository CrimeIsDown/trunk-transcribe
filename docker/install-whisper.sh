#!/bin/bash

set -eou pipefail

if [ -z "${DESIRED_CUDA:-}" ]; then
    if command -v nvidia-smi >/dev/null 2>&1; then
        # We could try to read the nvidia-smi output but there aren't many compatible PyTorch versions anyway
        DESIRED_CUDA="cu121"
    else
        echo "Could not find nvidia-smi, using CPU-only PyTorch" >&2
        DESIRED_CUDA="cpu"
    fi
fi

if [[ -n "${DESIRED_CUDA-}" ]] && [[ "${DESIRED_CUDA}" != "cu121" ]]; then
    EXTRA_INDEX_URL="--extra-index-url https://download.pytorch.org/whl/$DESIRED_CUDA"
else
    EXTRA_INDEX_URL=""
fi

pip3 install --use-pep517 $EXTRA_INDEX_URL --no-cache-dir torch torchaudio

pip3 install --use-pep517 $EXTRA_INDEX_URL --no-cache-dir git+https://github.com/openai/whisper.git@${WHISPER_VERSION:-ba3f3cd54b0e5b8ce1ab3de13e32122d0d5f98ab}
