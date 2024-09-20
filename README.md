# trunk-transcribe
Transcription of calls from trunk-recorder using OpenAI Whisper

<details>
  <summary>This is the software that powers <a href="https://crimeisdown.com/transcripts/search">CrimeIsDown.com Transcript Search</a> for Chicago. (open for screenshot)</summary>

  ![Transcript Search Page](https://user-images.githubusercontent.com/498525/215303132-9249123f-0fcd-41a4-b29e-8d9c5847e663.png)

</details>

This is experimental alpha-version software, use at your own risk. Expect breaking changes until version 1 is released.

## Architecture

1. `transcribe.sh` runs from trunk-recorder which makes a POST request to the API, passing along the call WAV and JSON
1. API creates a new task to transcribe the call and adds it to a queue (in RabbitMQ)
1. Worker(s) (running on a machine with a GPU) picks up the task from the queue and executes it, transcribing audio
1. As part of the task, worker makes an API call to Meilisearch to add the transcribed call to the search index
1. If notifications are configured, as part of the task the worker will send appropriate notifications

## Getting Started

*Prerequsites:*

- Docker and Docker Compose should be installed
- If using a GPU for OpenAI Whisper, also install the appropriate CUDA drivers (CUDA 12.1 currently supported)
- For Windows users running the worker: install [ffmpeg](https://www.gyan.dev/ffmpeg/builds/) and [sox](https://sourceforge.net/projects/sox/). Make sure these are added to your Windows PATH so they can be called directly from Python.

*Setup process:*

1. Clone repo
1. Copy `.env.example` to `.env` and set values
    1. `TELEGRAM_BOT_TOKEN` can be found by making a new bot on Telegram with @BotFather
1. Copy the `*.example` files in [`config`](./config/) to `.json` files and update them with your own settings. [See below](#configuration-files) for documentation on the specific settings.
1. Run `./make.sh start` to start (by default this will use your local GPU, see below for other options of running the worker)
    1. To use the CPU with Whisper.cpp (a CPU-optimized version of Whisper), comment out the `COMPOSE_FILE` line in your `.env`
1. On the machine running `trunk-recorder`, in the `trunk-recorder` config, set the following for the systems you want to transcribe:

    ```json
    "audioArchive": true,
    "callLog": true,
    "uploadScript": "transcribe.sh"
    ```
    An example upload script that can be used is available at [examples/transcribe.sh](./examples/transcribe.sh). Make sure to put that in the same location as the config.

    Additionally, make sure the systems are configured with a `talkgroupsFile`/`channelFile` and `unitTagsFile` so that the metadata sent to trunk-transcribe is complete with talkgroup/channel and unit names. You will be able to search on this metadata.

You can access a basic search page showing the calls at http://localhost:7700 (when prompted for an API key, enter the value of MEILI_MASTER_KEY in your .env). A custom search interface can also be built using the [Meilisearch API](https://docs.meilisearch.com/learn/getting_started/quick_start.html) and/or [InstantSearch.js](https://github.com/meilisearch/instant-meilisearch). This software may come with a customized search interface at a later date.

**To use the same interface as on [CrimeIsDown.com](https://crimeisdown.com/transcripts/search):** Go to [crimeisdown.com/settings](https://crimeisdown.com/settings) and update the `MEILISEARCH_URL` to http://localhost:7700 or whatever your publicly accessible URL is. Next, update `MEILISEARCH_KEY` to match the key in your `.env` file. Third, if using a different index name, update `MEILISEARCH_INDEX` to that index name. After doing all those updates, you should be able to return to the transcript search page and have it talk to your local copy instead.

There are numerous `docker-compose.*.yml` files in this repo for various configurations of the different components. Add `COMPOSE_FILE=` to your `.env` with the value being a list of docker-compose configurations separated by `:`, see `.env.example` for some common ones.

### Running workers using OpenAI's paid Whisper API

To use the paid Whisper API by OpenAI instead of running the worker on a machine with a GPU, set the following in your `.env` file:

```
# To use the paid OpenAI Whisper API instead of running the model locally
COMPOSE_FILE=docker-compose.server.yml:docker-compose.worker.yml:docker-compose.openai.yml

# OpenAI API key, if using the paid Whisper API
OPENAI_API_KEY=my-api-key
```

You may also want to set `CELERY_CONCURRENCY` to a higher number since the GPU is not a limitation on concurrency anymore.

### Running workers on Windows

The worker can be run on Windows if needed.

1. Make sure you have the ffmpeg and sox prerequisites installed, per the getting started section.
1. Follow steps 1-3 in the earlier getting started section to setup the repo and configuration.
1. Make a Python virtualenv in the repo:

    ```bat
    python -m venv .venv
    ```

1. Setup the Python dependencies by running `setup.bat`
1. Start the worker with `start.bat`

### Running workers on Vast.ai

The worker can be run on the cloud GPU service [vast.ai](https://vast.ai/). To get started, sign up for a vast.ai account. After that, update any settings in your `.env` such that a machine on the public internet could access the queue backend (*please ensure all services are protected by strong passwords*). Then, install the [Vast CLI](https://console.vast.ai/cli/) and login.

To start the autoscaler, set the following in your `.env`:

```bash
COMPOSE_FILE=docker-compose.server.yml:docker-compose.worker.yml:docker-compose.autoscaler.yml
# your API key from vast.ai, or omit to have it read from ~/.vast_api_key
VAST_API_KEY=
# Tune these settings as needed
AUTOSCALE_MIN_INSTANCES=1
AUTOSCALE_MAX_INSTANCES=10
```

If you want to maintain a constant number of instances on Vast.ai instead of autoscaling, just set the min and max instances to the same value.

### Viewing worker health

Some useful dashboards to check on the workers and queues:

- http://localhost:15672/ - RabbitMQ management (see queue statistics and graphs), login with guest/guest unless you have configured a custom RabbitMQ password
- http://localhost:5555/ - Flower, a Celery monitoring tool, use it to see details on current tasks and which tasks have failed, as well as current workers

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

Additional arguments to pass to the `transcribe()` function of the Whisper model. This JSON will get loaded into a Python dict and passed as kwargs to the function. Refer to https://github.com/openai/whisper/blob/main/whisper/transcribe.py and https://github.com/openai/whisper/blob/main/whisper/decoding.py#L72 for the available options.

File is cached in memory for 60 seconds upon reading from the worker's filesystem, so changes may not be shown instantly.

```jsonc
{
    "beam_size": 5
}
```

## Updating the search index

If a change is made to the search index settings or document data structure, it may be needed to re-index existing calls to migrate them to the new structure. This can be done by running the following:

```bash
docker compose run --rm api poetry run app/bin/reindex.py --update-settings
```

A more complex command, which updates calls in the `calls_demo` index without a `raw_transcript` attribute, and updating radio IDs for those calls from the chi_cfd system.

```bash
docker compose run --rm api poetry run app/bin/reindex.py --unit_tags chi_cfd ../trunk-recorder/config/cfd-radio-ids.csv --filter 'not hasattr(document, "raw_transcript")' --index calls_demo
```

This command can also be used to re-transcribe calls if improvements are made to the transcription accuracy. Beware that this will take a lot of resources, so consider adding a `--filter` argument with some Python code to limit what documents are re-transcribed.

```bash
docker compose run --rm api poetry run app/bin/reindex.py --retranscribe
```

Get the full list of arguments with `app/bin/reindex.py -h`.

## Contributing

To get a development environment going (or to just run the project without Docker):

```bash
sudo apt install pipx
pipx install poetry
poetry shell
# In the virtualenv that Poetry makes...
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
