#!/bin/bash

set -eou pipefail

if [ -z "${DESIRED_CUDA:-}" ]; then
    if command -v nvidia-smi >/dev/null 2>&1; then
        # We could try to read the nvidia-smi output but there aren't many compatible PyTorch versions anyway
        DESIRED_CUDA="cu117"
    else
        echo "Could not find nvidia-smi, using CPU-only PyTorch" >&2
        DESIRED_CUDA="cpu"
    fi
fi

if [[ -n "${DESIRED_CUDA-}" ]]; then
    EXTRA_INDEX_URL="--extra-index-url https://download.pytorch.org/whl/$DESIRED_CUDA"
else
    EXTRA_INDEX_URL=""
fi

pip3 install --use-pep517 $EXTRA_INDEX_URL torch torchvision torchaudio

pip3 install --use-pep517 git+https://github.com/shashikg/WhisperS2T.git@${WHISPER_VERSION:-v1.3.1}

# Modified from https://github.com/shashikg/WhisperS2T/blob/main/install_tensorrt.sh

###########################[ Installing OpenMPI ]###########################
apt-get update
apt-get -y install openmpi-bin libopenmpi-dev
rm -rf /var/lib/apt/lists/*

###########################[ Installing MPI4PY ]###########################
MPI4PY_VERSION="3.1.5"
RELEASE_URL="https://github.com/mpi4py/mpi4py/archive/refs/tags/${MPI4PY_VERSION}.tar.gz"
curl -L ${RELEASE_URL} | tar -zx -C /tmp
# Bypassing compatibility issues with higher versions (>= 69) of setuptools.
sed -i 's/>= 40\.9\.0/>= 40.9.0, < 69/g' /tmp/mpi4py-${MPI4PY_VERSION}/pyproject.toml
pip3 install /tmp/mpi4py-${MPI4PY_VERSION}
rm -rf /tmp/mpi4py*

###########################[ Installing TensorRT-LLM ]###########################
# Pin to version due to https://github.com/NVIDIA/TensorRT-LLM/issues/1442
pip3 install --no-cache-dir tensorrt_llm==0.9.0.dev2024040200 --extra-index-url https://pypi.nvidia.com
