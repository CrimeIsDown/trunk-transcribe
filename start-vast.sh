#!/bin/bash
set -eo pipefail

source .env.vast

INSTANCES=$(mktemp)
QUERY="rentable=true reliability>0.98 num_gpus=1 dlperf_usd>200 dph<=0.1 cuda_vers>=11.7"
vast search offers -n -i -o 'dph' "$QUERY" | tee $INSTANCES
sleep 5

cat $INSTANCES | \
tr -s ' ' | \
jq -c -Rn '
        input  | split(" ") as $head |
        inputs | split(" ") |
                to_entries |
                        map(.key = $head[.key]) |
                        [ .[] ] |
                from_entries' | \
head -n ${1:-1} | \
while read -r instance
do
    INSTANCE_ID="$(echo $instance | jq -r '.ID')"
    BID="$(echo $instance | jq -r '."$/hr" * 1.5')"

    IMAGE="crimeisdown/trunk-transcribe:main-medium.en-cu117"
    REQUEST=$(mktemp)

    set -x

    tee $REQUEST << EOF
{
    "client_id": "me",
    "image": "$IMAGE",
    "args": ["worker"],
    "env": {
        "TELEGRAM_BOT_TOKEN": "$TELEGRAM_BOT_TOKEN",
        "CELERY_BROKER_URL": "$CELERY_BROKER_URL",
        "CELERY_RESULT_BACKEND": "$CELERY_RESULT_BACKEND",
        "API_BASE_URL": "$API_BASE_URL",
        "TYPESENSE_HOST": "$TYPESENSE_HOST",
        "TYPESENSE_API_KEY": "$TYPESENSE_API_KEY",
        "S3_ENDPOINT": "$S3_ENDPOINT",
        "S3_PUBLIC_URL": "$S3_PUBLIC_URL",
        "AWS_ACCESS_KEY_ID": "$AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY": "$AWS_SECRET_ACCESS_KEY",
        "S3_BUCKET": "$S3_BUCKET"
    },
    "price": $BID,
    "disk": 0.5,
    "runtype": "args"
}
EOF

    curl -s --fail-with-body --request PUT \
        --url "https://console.vast.ai/api/v0/asks/$INSTANCE_ID/?api_key=$(cat ~/.vast_api_key)" \
        --data-binary @$REQUEST

    set +x

    rm $REQUEST
done

rm $INSTANCES

watch -n 5 vast show instances
