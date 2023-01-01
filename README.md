# trunk-transcribe
Transcription of calls from trunk-recorder, based on OpenAI Whisper

WORK IN PROGRESS

## Getting Started

1. Clone repo
1. Copy `.env.example` to `.env` and set values
    1. `TELEGRAM_BOT_TOKEN` can be found by making a new bot on Telegram with @BotFather
1. Update config files in [`config`](./config/) with your own settings
    1. Create Telegram channels and set talkgroup -> channel mappings
1. Run `docker-compose up -d` to start
1. On the machine running `trunk-recorder`, create a shell script using the example below
1. In the `trunk-recorder` config, set the `uploadScript` to the newly created shell script, and set `"audioArchive": true`

### `uploadScript` example

```bash
#!/bin/bash
curl -s --connect-timeout 1 --request POST \
    --url "http://127.0.0.1:8004/tasks" \
    --header 'Content-Type: multipart/form-data' \
    --form call_audio=@$1 \
    --form call_json=@$2 &>/dev/null &
disown
```
