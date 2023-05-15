#!/bin/bash

set -eou pipefail

pip3 install --use-pep517 git+https://github.com/guillaumekln/faster-whisper.git@${WHISPER_VERSION:-6a2da9a95cf807d529ea97b2ce1c46103a88e158}
