#!/bin/bash

set -eou pipefail

pip3 install --use-pep517 git+https://github.com/SYSTRAN/faster-whisper.git@${WHISPER_VERSION:44f7e589478866546bfcd1d105e254a74e2caad5}
