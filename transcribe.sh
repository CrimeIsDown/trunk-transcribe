#!/bin/bash
set -eo pipefail

wav="$1"
json="$2"

if ! [[ -f $wav ]] || ! [[ -f $json ]]; then
  echo "Could not find file(s) $wav $json, make sure \`audioArchive\` and \`callLog\` are both set to true" >&2
  exit 1
fi

if ! which jq &>/dev/null; then
  # Try to install jq if it's not already installed
  curl -Ls https://github.com/stedolan/jq/releases/download/jq-1.6/jq-linux64 > /usr/local/bin/jq
  chmod +x /usr/local/bin/jq
fi

SYSTEM="$(jq -r '.short_name' $json)"
TALKGROUP="$(jq -r '.talkgroup' $json)"

# Call too short to be transcribed
if [[ "$(jq -r '.call_length' $json)" -lt "${MIN_CALL_LENGTH:-2}" ]]; then
  exit
fi

if \
  true
  # Optionally, you can add filters:
  # [[ "$SYSTEM" == "chi_cfd" ]] || \
  # ([[ "$SYSTEM" == "chi_cpd" ]] && [[ "$TALKGROUP" -lt "16" ]]) || \
  # [[ "$TALKGROUP" == "9051" ]] \
; then
  # Define these environment variables or replace them with your values
  API_BASE_URL="${API_BASE_URL}"
  API_KEY="${API_KEY}"

  curl -s --connect-timeout 1 --request POST \
      --url "$API_BASE_URL/tasks" \
      --header "Authorization: Bearer $API_KEY" \
      --header 'Content-Type: multipart/form-data' \
      --form call_audio=@$wav \
      --form call_json=@$json &>/dev/null &
  disown
  # We run the curl command as a background process and disown it to not hang up trunk-recorder.
fi
