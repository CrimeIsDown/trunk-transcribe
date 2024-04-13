#!/bin/bash
set -e

minio server /data --console-address ":9001" &
SERVER_PID=$!

until /usr/bin/mc alias set minio http://127.0.0.1:9000 ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD}
do
    sleep 1
done
/usr/bin/mc mb minio/${S3_BUCKET} ||:
/usr/bin/mc anonymous set none minio/${S3_BUCKET}
/usr/bin/mc anonymous set download minio/${S3_BUCKET}/*
/usr/bin/mc cp /etc/hostname minio/${S3_BUCKET}/init-complete

wait $SERVER_PID
