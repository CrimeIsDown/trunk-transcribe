#!/bin/bash
set -eo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

source .env.vast

START=${1:-1}
END=$2

if [[ -z "$END" ]]; then
    END=$START
    START=1
fi

EXISTING_INSTANCES="$(vast show instances --raw | jq -r '.[].machine_id' | paste -sd\| -)"

if [[ "$START" == "--min-instances" ]]; then
    DESIRED_COUNT=$END
    CURRENT_COUNT=$(curl --fail-with-body -Ss 'http://crimeisdown:5555/api/workers?refresh=true&status=true' | jq -r 'to_entries | map(select(.value == true)) | length')

    START=1
    END=$(($DESIRED_COUNT - $CURRENT_COUNT + 1))

    if [ $END -lt 2 ]; then
        echo "Enough instances running, exiting"
        exit
    fi
fi

if [[ -z "$EXISTING_INSTANCES" ]]; then
    EXISTING_INSTANCES="no-instances"
fi

echo -e "Planning to start these instances:\n"

INSTANCES=$(mktemp)
QUERY="rentable=true rented=false reliability>0.98 num_gpus=1 dlperf_usd>200 dph<=0.1 cuda_vers>=11.7"
vast search offers -n -i -o 'dph' "$QUERY" | \
grep -Ev "\b$EXISTING_INSTANCES\b" | \
sed -n "1,1p;$((${START} + 1)),$((${END} + 1))p;$((${END} + 2))q" | tee $INSTANCES
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
sed -n "${START},${END}p;$((${END} + 1))q" | \
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
        "CELERY_HOSTNAME": "celery-$(git rev-parse --short HEAD)@vast-$INSTANCE_ID",
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
