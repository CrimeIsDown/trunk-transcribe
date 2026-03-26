# trunk-transcribe
Transcription of calls from trunk-recorder using backend-specific ASR workers

<details>
  <summary>This is the software that powers <a href="https://crimeisdown.com/transcripts/search">CrimeIsDown.com Transcript Search</a> for Chicago. (open for screenshot)</summary>

  ![Transcript Search Page](https://user-images.githubusercontent.com/498525/215303132-9249123f-0fcd-41a4-b29e-8d9c5847e663.png)

</details>

This is experimental alpha-version software, use at your own risk. Expect breaking changes until version 1 is released.

## Architecture

1. `transcribe.sh` runs from trunk-recorder which makes a POST request to the API, passing along the call WAV and JSON
1. API resolves a `transcription_backend` for the request and adds the transcription job to the matching RabbitMQ queue
1. A backend-specific worker stack consumes exactly one backend queue: `transcribe_whisper`, `transcribe_api`, `transcribe_qwen`, or `transcribe_voxtral`
1. The worker either forwards audio to a sibling/local ASR HTTP service or calls a vendor-hosted API, then normalizes the response
1. The `post_transcribe` worker stores the results in search and sends notifications

See [docs/architecture.md](./docs/architecture.md) for Mermaid diagrams covering the full runtime topology and the current transcript provider/model mapping.

## Getting Started

*Prerequsites:*

- Docker and Docker Compose should be installed
- If using a GPU-backed ASR server, also install the appropriate CUDA drivers (CUDA 12.1 currently supported)
- For Windows users running the worker: install [ffmpeg](https://www.gyan.dev/ffmpeg/builds/) and [sox](https://sourceforge.net/projects/sox/). Make sure these are added to your Windows PATH so they can be called directly from Python.

*Setup process:*

1. Clone repo
1. Copy `.env.example` to `.env` and set values
    1. `TELEGRAM_BOT_TOKEN` can be found by making a new bot on Telegram with @BotFather
1. Copy the `*.example` files in [`config`](./config/) to `.json` files and update them with your own settings. [See below](#configuration-files) for documentation on the specific settings.
1. Run `./make.sh start` to start the default stack
    1. By default this starts the API services, a `post_transcribe` worker, a Whisper worker, GPU support for the Whisper worker, and MinIO
    1. To run a different backend worker, update `COMPOSE_FILE` in `.env` to swap `docker-compose.worker-whisper.yml` for `docker-compose.worker-api.yml`, `docker-compose.worker-qwen.yml`, or `docker-compose.worker-voxtral.yml`
1. On the machine running `trunk-recorder`, in the `trunk-recorder` config, set the following for the systems you want to transcribe:

    ```json
    "audioArchive": true,
    "callLog": true,
    "uploadScript": "./transcribe.sh"
    ```
    An example upload script that can be used is available at [examples/transcribe.sh](./examples/transcribe.sh). Make sure to put that in the same location as the config.

    Additionally, make sure the systems are configured with a `talkgroupsFile`/`channelFile` and `unitTagsFile` so that the metadata sent to trunk-transcribe is complete with talkgroup/channel and unit names. You will be able to search on this metadata.

You can access a basic search page showing the calls at http://localhost:7700 (when prompted for an API key, enter the value of MEILI_MASTER_KEY in your .env). A custom search interface can also be built using the [Meilisearch API](https://docs.meilisearch.com/learn/getting_started/quick_start.html) and/or [InstantSearch.js](https://github.com/meilisearch/instant-meilisearch). This software may come with a customized search interface at a later date.

**To use the same interface as on [CrimeIsDown.com](https://crimeisdown.com/transcripts/search):** Go to [crimeisdown.com/settings](https://crimeisdown.com/settings) and update the `MEILISEARCH_URL` to http://localhost:7700 or whatever your publicly accessible URL is. Next, update `MEILISEARCH_KEY` to match the key in your `.env` file. Third, if using a different index name, update `MEILISEARCH_INDEX` to that index name. After doing all those updates, you should be able to return to the transcript search page and have it talk to your local copy instead.

### Scanner Transcript AI Analysis

A dedicated `chat-ui` container now hosts the transcript-analysis agent used by the frontend's embedded CopilotKit panel on the search page.

By default, this service is included in `docker-compose.server.yml` and runs on `http://localhost:7932` (or `CHAT_UI_PORT` if overridden).

The AI panel analyzes the exact active search query, refinements, hierarchy selection, and time window, then paginates through matching transcripts up to the configured analysis cap.

There are numerous `docker-compose.*.yml` files in this repo for various configurations of the different components. Add `COMPOSE_FILE=` to your `.env` with the value being a list of docker-compose configurations separated by `:`, see `.env.example` for some common ones.

### Backend-specific workers

Each transcription machine should run exactly one backend-specific worker stack:

- `docker-compose.worker-whisper.yml` consumes `transcribe_whisper` and runs [`speaches`](https://github.com/speaches-ai/speaches)
- `docker-compose.worker-api.yml` consumes `transcribe_api` and forwards to OpenAI, Deepgram, or DeepInfra
- `docker-compose.worker-qwen.yml` consumes `transcribe_qwen` and runs [`trunk-reporter/qwen3-asr-server`](https://github.com/trunk-reporter/qwen3-asr-server)
- `docker-compose.worker-voxtral.yml` consumes `transcribe_voxtral` and runs [`vllm serve`](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html) for [`mistralai/Voxtral-Mini-4B-Realtime-2602`](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602)

The shared `docker-compose.worker.yml` service is the `post_transcribe` worker. Keep at least one of those running somewhere in the deployment.

To add another Whisper machine:

```bash
COMPOSE_FILE=docker-compose.worker-whisper.yml:docker-compose.gpu.yml
docker compose up -d
```

The default Whisper stack uses `ghcr.io/speaches-ai/speaches:latest-cuda` and calls its OpenAI-compatible `/v1/audio/transcriptions` endpoint. To run Whisper on CPU, set `ASR_WHISPER_IMAGE=ghcr.io/speaches-ai/speaches:latest-cpu` and omit `docker-compose.gpu.yml`.

To add an API-forwarding machine:

```bash
COMPOSE_FILE=docker-compose.worker-api.yml
docker compose up -d
```

The API worker does not need `docker-compose.gpu.yml`. Set `WHISPER_IMPLEMENTATION` to `openai` or `deepinfra`, then provide the matching API key.

To add another Qwen machine:

```bash
COMPOSE_FILE=docker-compose.worker-qwen.yml:docker-compose.gpu.yml
docker compose up -d
```

If you want the Qwen stack to run without a GPU, set `ASR_QWEN_IMAGE=ghcr.io/trunk-reporter/qwen3-asr-server:cpu` and omit `docker-compose.gpu.yml`.

To add another Voxtral machine:

```bash
COMPOSE_FILE=docker-compose.worker-voxtral.yml:docker-compose.gpu.yml
docker compose up -d
```

The default Voxtral stack uses `vllm/vllm-openai:latest` plus Mistral's recommended serve flags for `mistralai/Voxtral-Mini-4B-Realtime-2602`. If your Hugging Face access requires authentication, set `HF_TOKEN` in `.env` so vLLM can download the model weights.

### Running workers using OpenAI's paid Whisper API

To use the paid Whisper API by OpenAI, run the API backend instead of the Whisper sidecar worker and set the following in your `.env` file:

```
# Run the regular post worker plus an API-forwarding worker
COMPOSE_FILE=docker-compose.server.yml:docker-compose.worker.yml:docker-compose.worker-api.yml

# Route new jobs to the API queue
DEFAULT_TRANSCRIPTION_BACKEND=api

# Use the OpenAI speech API
WHISPER_IMPLEMENTATION=openai
OPENAI_API_KEY=my-api-key
```

You may also want to set `CELERY_CONCURRENCY` to a higher number since the worker is only forwarding requests.

### Running workers using DeepInfra's Whisper API

To use DeepInfra's OpenAI-compatible Whisper API, run the API backend and set the following in your `.env` file:

```
# Route jobs to the API queue
DEFAULT_TRANSCRIPTION_BACKEND=api

# Switch to DeepInfra implementation
WHISPER_IMPLEMENTATION=deepinfra

# DeepInfra API key
DEEPINFRA_API_KEY=my-api-key

# Optional model override (defaults to openai/whisper-large-v3-turbo)
# WHISPER_MODEL=openai/whisper-large-v3-turbo
```

### Running workers on Windows

The worker can be run on Windows if needed.

1. Clone the repo or otherwise download the zip file from GitHub and extract it.
1. Copy `.env.example` to `.env` and update it with the appropriate settings. Your `COMPOSE_FILE` line should be set to `COMPOSE_FILE=docker-compose.worker-whisper.yml:docker-compose.gpu.yml`.
1. Choose one of the two paths below for actually running the worker.

#### Using Docker / WSL (Recommended)

The recommended way is to use Docker for Windows which has Docker Compose support, and so there's no Python setup needed.

1. [Follow these instructions](https://docs.docker.com/desktop/install/windows-install/) to install Docker Desktop.
1. Open a terminal in the trunk-transcribe directory.
1. In your terminal, run `docker compose up -d` to start the worker.
1. Verify the container is running properly by looking at the status and logs in the Docker Desktop application.

#### Using native Python

(this is not frequently tested, so this may require some troubleshooting)

1. Install all the prerequsites per the Prerequsites section above.
1. [Download and install Python 3.12](https://www.python.org/downloads/) if it is not already installed.
1. [Install uv with their Windows standalone installer](https://docs.astral.sh/uv/getting-started/installation/).
1. Setup the Python dependencies by running `setup.bat`
1. Start the worker with `start.bat`

### Running workers on Vast.ai

The worker can be run on the cloud GPU service [vast.ai](https://vast.ai/). To get started, sign up for a vast.ai account. After that, update any settings in your `.env` such that a machine on the public internet could access the queue backend (*please ensure all services are protected by strong passwords*). Then, install the [Vast CLI](https://console.vast.ai/cli/) and login.

To start the autoscaler, set the following in your `.env`:

```bash
COMPOSE_FILE=docker-compose.server.yml:docker-compose.worker.yml:docker-compose.autoscaler.yml
# your API key from vast.ai, or omit to have it read from ~/.vast_api_key
VAST_API_KEY=
# One autoscaler should manage one backend queue
AUTOSCALE_BACKEND=whisper
AUTOSCALE_QUEUE=transcribe_whisper
AUTOSCALE_WORKER_IMAGE=ghcr.io/crimeisdown/trunk-transcribe:main-whisper-large-v3-cuda_12.1.0
# Tune these settings as needed
AUTOSCALE_MIN_INSTANCES=1
AUTOSCALE_MAX_INSTANCES=10
```

The Vast autoscaler is only useful for GPU-backed backends. The `api` backend is just request forwarding, so run `docker-compose.worker-api.yml` on standard CPU compute instead.

If you want to maintain a constant number of instances on Vast.ai instead of autoscaling, just set the min and max instances to the same value. Run a separate autoscaler per backend when you want to scale more than one backend queue.

### Viewing worker health

Some useful dashboards to check on the workers and queues:

- http://localhost:15672/ - RabbitMQ management (see queue statistics and graphs), login with guest/guest unless you have configured a custom RabbitMQ password
- http://localhost:5555/ - Flower, a Celery monitoring tool, use it to see details on current tasks and which tasks have failed, as well as current workers

### Updating and Postgres 18 Upgrade

Use `./update.sh` to pull the latest changes and restart services. As part of that script, if you already have a Postgres data volume created with the old layout (`/var/lib/postgresql/data`), it will automatically run `pg_upgrade` to migrate it to the Postgres 18+ layout (`/var/lib/postgresql/<major>/data`) without losing data.

## Configuration Files

### notifications.json

Configuration used to send notifications of calls to various services. You can also receive alerts when a transcript mentions a certain keyword, or is within a certain distance/driving time of your specified location.

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
                // NOTE: If both keywords and location.radius / location.travel_time are specified, then it will AND the two alert conditions together
                "keywords": [
                    // A list of keywords to find in the transcript, can be multiple words - case insensitive search
                    "working fire"
                ],
                "location": {
                    // Latitude and longitude of the point to compare the call location to (e.g. your current location)
                    "geo": {
                        "lat": 41.8,
                        "lng": -87.7
                    },
                    // NOTE: radius will get ANDed with travel_time if both are specified, so only include the keys you want to be conditions
                    // Radius in miles, will notify for calls under 2 miles away
                    "radius": 2,
                    // Travel time in seconds, will notify for calls within a 10 minute drive (with current traffic conditions)
                    // This requires a Google API key with the Routes API enabled
                    "travel_time": 600
                }
            }
        ]
    }
}
```

### whisper.json

Legacy decode options for direct Whisper integrations. Server-based backends ignore these values, so this file is only useful if you add a backend that consumes `decode_options`.

File is cached in memory for 60 seconds upon reading from the worker's filesystem, so changes may not be shown instantly.

```jsonc
{
    "beam_size": 5
}
```

## Updating the search index

If a change is made to the search index settings or document data structure, it may be needed to re-index existing calls to migrate them to the new structure. This can be done by running the following:

```bash
docker compose run --rm api uv run --directory backend python scripts/reindex.py --update-settings
```

If the talkgroup search materialized view needs to be rebuilt after a schema change or large backfill, refresh it with:

```bash
docker compose run --rm api uv run --directory backend python scripts/refresh-talkgroup-search.py
```

A more complex command, which updates calls in the `calls_demo` index without a `raw_transcript` attribute, and updating radio IDs for those calls from the chi_cfd system.

```bash
docker compose run --rm api uv run --directory backend python scripts/reindex.py --unit_tags chi_cfd ../trunk-recorder/config/cfd-radio-ids.csv --filter 'not hasattr(document, "raw_transcript")' --index calls_demo
```

This command can also be used to re-transcribe calls if improvements are made to the transcription accuracy. Beware that this will take a lot of resources, so consider adding a `--filter` argument with some Python code to limit what documents are re-transcribed.

```bash
docker compose run --rm api uv run --directory backend python scripts/reindex.py --retranscribe
```

Get the full list of arguments with `uv run --directory backend python scripts/reindex.py -h`.

## Contributing

To get a development environment going (or to just run the project without Docker)...

First, [install uv](https://docs.astral.sh/uv/getting-started/installation/). Once you have it installed:

```bash
# Create a virtualenv
uv venv
# Activate the virtualenv
source .venv/bin/activate
# In the virtualenv that uv makes...
./make.sh deps
```

Some helpful `make` commands:

```bash
# Format code to adhere to code style
./make.sh lint
# Run all tests
./make.sh test
# Restart API and worker
./make.sh restart
# Do a restart, and then run tests (do this after making a change and needing to run tests again)
./make.sh retest
```

PRs are welcome.
