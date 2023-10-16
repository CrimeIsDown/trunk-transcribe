#!/bin/bash

set -eou pipefail

pip3 install --use-pep517 git+https://github.com/guillaumekln/faster-whisper.git@${WHISPER_VERSION:-v0.9.0}
