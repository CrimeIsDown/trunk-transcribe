#!/bin/bash
set -e

cd "$(dirname "$0")"

CLIPS_DIR="${CLIPS_DIR:-/tmp/clips}"
mkdir -p $CLIPS_DIR

# Environment variables
# AUDIO_THRESHOLD_START: Silence threshold to start clipping audio
# AUDIO_THRESHOLD_END: Silence threshold to end clipping audio
# AUDIO_THRESHOLD: Silence threshold for both start and end clipping audio
# AUDIO_DURATION: Duration of audio clips
# CALL_LENGTH_THRESHOLD: Minimum call length to process
# API_BASE_URL: Base URL for trunk-transcribe API
# CLIPS_DIR: Directory to store audio clips

clip_audio() {
  echo "Starting ffmpeg and sox..."
  if [ -z "$AUDIO_THRESHOLD_START" ]; then
    AUDIO_THRESHOLD_START=${AUDIO_THRESHOLD:-0}
  fi
  if [ -z "$AUDIO_THRESHOLD_END" ]; then
    AUDIO_THRESHOLD_END=${AUDIO_THRESHOLD:-0}
  fi
  set -x
  ffmpeg \
    -hide_banner -loglevel warning \
    -i "$STREAM_URL" \
    -filter:a 'speechnorm' \
    -ac 1 \
    -acodec pcm_s16le \
    -f wav \
    - | \
  sox -t wav - \
    "${CLIPS_DIR}/${STREAM_NAME}_.wav" \
    silence 1 0 ${AUDIO_THRESHOLD_START:-0}% 1 00:00:0${AUDIO_DURATION:-3} ${AUDIO_THRESHOLD_END:-0}% \
    : newfile : restart
  set +x
}

upload_to_transcribe() {
  ./transcribe.sh "$wav_file" $call_json && \
  echo "Successfully uploaded to trunk-transcribe"
}

process_call() {
  wav_file="$2"
  # Check call length
  call_length=$(soxi -D $wav_file)
  if (( $(echo "$call_length < ${CALL_LENGTH_THRESHOLD:-0.8}" | bc -l) )); then
    echo "$wav_file is ${call_length}s, shorter than ${CALL_LENGTH_THRESHOLD:-0.8}s, skipping" >&2
    return
  fi
  stop_time=$(date -r $wav_file "+%s")
  call_length_int=$(printf "%.0f" $call_length)
  start_time=$(($stop_time - $call_length_int))

  FREQ=$(jq -r '.freq' "$1")
  TALKGROUP_ID=$(jq -r '.talkgroup' "$1")

  call_json="$(dirname $wav_file)/${TALKGROUP_ID}-${start_time}_${FREQ}-call_0.json"

  jq -s '.[0] * .[1]' "$1" - << EOF | jq 'del(.source_url)' > $call_json
{
  "start_time": $start_time,
  "stop_time": $stop_time,
  "call_length": $call_length_int,
  "freqList": [{ "freq": $FREQ.000000, "time": $start_time, "pos": 0.00, "len": $call_length, "error_count": "0", "spike_count": "0"}],
  "srcList": [{"src": -1, "time": $start_time, "pos": 0.00, "emergency": 0, "signal_system": "", "tag": ""}]
}
EOF

  echo "Uploading $wav_file"

  if [ -n "$API_BASE_URL" ]; then
    upload_to_transcribe
  fi
  rm $call_json
}

export STREAM_NAME="$(basename ${1%.*})"
export STREAM_URL="$(jq -r '.source_url' ${1})"
export API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"

# if the stream_url does not contain mp3, then find the mp3 stream
# curl the stream_url and find a mp3 url
if [[ $STREAM_URL != *"mp3"* ]]; then
  STREAM_URL_FOUND=$(curl -s $STREAM_URL | grep -oP '(?<=<audio class="bcfy_web_player" preload="none" src=")[^"]+' )
  if [ -z "$STREAM_URL" ]; then
    echo "Could not find mp3 stream in $STREAM_URL"
    exit 1
  fi
  echo "Found mp3 stream: $STREAM_URL_FOUND"
  export STREAM_URL=$STREAM_URL_FOUND
fi

clip_audio $1 &

while true; do
  for file in $(find ${CLIPS_DIR} -type f -name "${STREAM_NAME}_*.wav" -size +1b); do
    if ! fuser $file > /dev/null; then
      process_call "$1" "$file"
      rm $file
    fi
  done
  sleep 1
done
