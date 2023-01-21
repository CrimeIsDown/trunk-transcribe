#!/bin/bash
set -e

cd "$(dirname "${BASH_SOURCE[0]}")"

source .env.vast

START=${1:-1}
END=$2

if [[ -z "$END" ]]; then
    END=$START
    START=1
fi

SHOW_INSTANCES_OUTPUT=$(mktemp)
vast show instances --raw > $SHOW_INSTANCES_OUTPUT

EXISTING_INSTANCES="$(jq -r '.[].machine_id' $SHOW_INSTANCES_OUTPUT | paste -sd\| -)"

if [[ "$START" == "--min-instances" ]]; then
    jq -r '.[] | select(.actual_status == "exited") | .id' $SHOW_INSTANCES_OUTPUT | xargs -r -n 1 vast destroy instance

    DESIRED_COUNT=$END
    CURRENT_COUNT=$(curl --fail-with-body -Ss 'http://crimeisdown:5555/api/workers?refresh=true&status=true' | jq -r 'to_entries | map(select(.value == true)) | length')

    START=1
    END=$(($DESIRED_COUNT - $CURRENT_COUNT + 1))

    if [ $END -lt 2 ]; then
        if [ -t 1 ]; then
            echo "Enough instances running, exiting"
        fi
        exit
    fi
fi

echo -e "Planning to start these instances:\n"

INSTANCES=$(mktemp)
QUERY="rentable=true rented=false reliability>0.98 num_gpus=1 gpu_ram>8 dlperf_usd>200 dph<=0.1 cuda_vers>=11.7"
vast search offers -n -i -o 'dph' "$QUERY" | \
if [[ -n "$EXISTING_INSTANCES" ]]; then grep -Ev "\b$EXISTING_INSTANCES\b"; else cat; fi | \
sed -n "1,1p;$((${START} + 1)),$((${END} + 1))p;$((${END} + 2))q" | tee $INSTANCES

if [ -t 1 ]; then
    sleep 5
fi

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

    cat << EOF > $REQUEST
{
    "client_id": "me",
    "image": "$IMAGE",
    "args": ["worker"],
    "env": {
        "CELERY_HOSTNAME": "celery-$(git rev-parse --short HEAD)@vast-$INSTANCE_ID",
EOF

    while read line; do
        KEY="$(echo "$line" | cut -d= -f1)"
        VALUE="$(echo "$line" | cut -d= -f2-)"
        echo "        \"$KEY\": \"$VALUE\"," >> $REQUEST
    done < .env.vast
    # Remove the trailing comma
    head -c -2 $REQUEST > $REQUEST.new
    # Add back the newline
    echo >> $REQUEST.new
    mv $REQUEST.new $REQUEST

    cat << EOF >> $REQUEST
    },
    "price": $BID,
    "disk": 0.5,
    "runtype": "args"
}
EOF

    cat $REQUEST

    set -x

    curl -s --fail-with-body --request PUT \
        --url "https://console.vast.ai/api/v0/asks/$INSTANCE_ID/?api_key=$(cat ~/.vast_api_key)" \
        --data-binary @$REQUEST

    set +x

    rm $REQUEST
done

rm $INSTANCES

if [ -t 1 ]; then
    watch -n 5 -w vast show instances
fi
