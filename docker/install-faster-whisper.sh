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

pip3 install --use-pep517 --no-cache-dir git+https://github.com/SYSTRAN/faster-whisper.git@${WHISPER_VERSION:-v1.0.2}
