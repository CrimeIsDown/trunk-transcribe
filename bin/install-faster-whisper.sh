#!/bin/bash

set -eou pipefail

pip3 install --use-pep517 git+https://github.com/SYSTRAN/faster-whisper.git@${WHISPER_VERSION:-v1.0.1}
