#!/bin/bash

set -eou pipefail

pip3 install --use-pep517 git+https://github.com/guillaumekln/faster-whisper.git@${WHISPER_VERSION:-358d373691c95205021bd4bbf28cde7ce4d10030}
