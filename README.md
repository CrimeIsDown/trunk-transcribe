# trunk-transcribe
Transcription of calls from trunk-recorder using OpenAI Whisper

This is the software that powers [CrimeIsDown.com Transcript Search](https://crimeisdown.com/transcripts/search) for Chicago.

This is experimental alpha-version software, use at your own risk. Expect breaking changes until version 1 is released.

## Architecture

1. `transcribe.sh` runs from trunk-recorder which makes a POST request to the API, passing along the call WAV and JSON
1. API creates a new task to transcribe the call and adds it to a queue (in RabbitMQ)
1. Worker(s) (running on a machine with a GPU) picks up the task from the queue and executes it, transcribing audio
1. As part of the task, worker makes an API call to Meilisearch to add the transcribed call to the search index
1. If notifications are configured, as part of the task the worker will send appropriate notifications

## Getting Started

Prerequsites: You should have Docker and Docker Compose installed, as well as the appropriate CUDA drivers if using a GPU for OpenAI Whisper.

1. Clone repo
1. Copy `.env.example` to `.env` and set values
    1. `TELEGRAM_BOT_TOKEN` can be found by making a new bot on Telegram with @BotFather
1. Copy the `*.example` files in [`config`](./config/) to `.json` files and update them with your own settings.
1. Run `make start` to start (by default this will use your local GPU, see below for other options of running the worker)
1. On the machine running `trunk-recorder`, in the `trunk-recorder` config, set the following for the systems you want to transcribe:

    ```json
    "audioArchive": true,
    "callLog": true,
    "uploadScript": "transcribe.sh"
    ```
    An example upload script that can be used is available at [transcribe.sh](./transcribe.sh). Make sure to put that in the same location as the config.

You can access a basic search page showing the calls at http://localhost:7700 (when prompted for an API key, enter the value of MEILI_MASTER_KEY in your .env). A custom search interface can also be built using the [Meilisearch API](https://docs.meilisearch.com/learn/getting_started/quick_start.html) and/or [InstantSearch.js](https://github.com/meilisearch/instant-meilisearch).

### Running workers on Windows

The worker can be run on Windows if needed.

1. Follow steps 1-3 in the earlier getting started section to setup the repo and configuration.
1. Make a Python virtualenv in the repo:

    ```bat
    python -m venv .venv
    ```

1. Setup the Python dependencies by running `setup.bat`
1. Start the worker with `start.bat`

### Running workers on Vast.ai

The worker can be run on the cloud GPU service [vast.ai](https://vast.ai/). To get started, sign up for a vast.ai account. Next, create a copy of your `.env` called `.env.vast`. Update any settings such that a machine on the public internet could access the API and queue backend (*please ensure all services are protected by strong passwords*). Then, install the [Vast CLI](https://console.vast.ai/cli/) and login.

Run `bin/autoscale-vast.py` to start workers and autoscale them as needed. Run `bin/autoscale-vast.py -h` to see available arguments.

To keep the autoscaler running, set the following in your `.env`:

```bash
COMPOSE_FILE=COMPOSE_FILE=docker-compose.yml:docker-compose.noworker.yml:docker-compose.autoscaler.yml
# your API key from vast.ai, or omit to have it read from ~/.vast_api_key
VAST_API_KEY=
# Tune these settings as needed
AUTOSCALE_MIN_INSTANCES=1
AUTOSCALE_MAX_INSTANCES=10
AUTOSCALE_THROUGHPUT=20
```

### Viewing worker health

Some useful dashboards to check on the workers and queues:

- http://localhost:15672/ - RabbitMQ management (see queue statistics and graphs), login with guest/guest unless you have configured a custom RabbitMQ password
- http://localhost:5555/ - Flower, a Celery monitoring tool, use it to see details on current tasks and which tasks have failed, as well as current workers

## Configuration Files

### notifications.json

Configuration used to send notifications of calls to various services.

File is cached in memory for 60 seconds upon calling the API (or reading from disk if that fails), so changes may not be shown instantly.

```jsonc
{
    // Key - a regex to match the associated talkgroup and system
    // Will be matched against a string "talkgroup@short_name", e.g. 1@chi_cfd
    // See notifications.json.example for some more complex regexes
    "^1@chi_cfd$": {
        "channels": [
            // Notification channels to send the transcript to (with associated audio)
            // See https://github.com/caronc/apprise/blob/master/README.md#supported-notifications for a full list
            // Telegram example (only tested integration so far)
            "tgram://$TELEGRAM_BOT_TOKEN/chat_id"
        ],
        "append_talkgroup": true,
        "alerts": [
            {
                "channels": [
                    // Notification channels to send the transcript to (with link to audio), if keywords matched
                    // See https://github.com/caronc/apprise/blob/master/README.md#supported-notifications for a full list
                    // Telegram example (only tested integration so far)
                    "tgram://$TELEGRAM_BOT_TOKEN/chat_id"
                ],
                "keywords": [
                    // A list of keywords to find in the transcript, can be multiple words - case insensitive search
                    "working fire"
                ]
            }
        ]
    }
}
```

### whisper.json

Additional arguments to pass to the `transcribe()` function of the Whisper model. This JSON will get loaded into a Python dict and passed as kwargs to the function. Refer to https://github.com/openai/whisper/blob/main/whisper/transcribe.py and https://github.com/openai/whisper/blob/main/whisper/decoding.py#L72 for the available options.

File is cached in memory for 60 seconds upon reading from the worker's filesystem, so changes may not be shown instantly.

```jsonc
{
    "beam_size": 5
}
```

## Contributing

To get a development environment going (or to just run the project without Docker):

```bash
pip3 install poetry
poetry shell
# In the virtualenv that Poetry makes...
make deps
```

Some helpful `make` commands:

```bash
# Format code to adhere to code style
make fmt
# Run all tests
make test
# Restart API and worker
make restart
# Do a restart, and then run tests (do this after making a change and needing to run tests again)
make restart-and-test
```

PRs are welcome.
