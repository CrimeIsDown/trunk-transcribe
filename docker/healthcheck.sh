#!/bin/bash
if ! curl -f --retry 3 --max-time 5 --retry-delay 5 --retry-max-time 30 "http://127.0.0.1:8000/healthz"; then
    # First try graceful shutdown, then hard shutdown
    kill -s 15 -1 && (sleep 10; kill -s 9 -1)
fi
