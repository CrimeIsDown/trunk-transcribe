# Worker Backend Architecture Plan

Status: proposed
Date: 2026-03-22

## Goal

Allow an arbitrary set of computers to join the transcription pool by starting a backend-specific worker stack. Each machine should immediately help with the shared load for the backend it supports.

This plan does not change code yet. It defines the target architecture and the implementation checklist.

## Core Model

- Route transcription jobs by backend queue, not by one global GPU queue.
- Each machine runs one backend-specific worker stack.
- A worker stack includes:
  - one Celery worker consuming one backend queue
  - any local inference service needed for that backend
- Vast autoscaling launches more workers of the same backend type by watching that backend queue.

## Queue Names

- `transcribe_whisper`
- `transcribe_qwen`
- `transcribe_voxtral`
- `post_transcribe`

## Backend Model

Supported backend values:

- `whisper`
- `qwen`
- `voxtral`

Default backend:

- `whisper`

## Worker Stack Compose Files

Add these compose files:

- `docker-compose.worker-whisper.yml`
- `docker-compose.worker-qwen.yml`
- `docker-compose.worker-voxtral.yml`

Each compose file should fully define the services needed on that machine.

### `docker-compose.worker-whisper.yml`

Services:

- `worker-whisper`
- `asr-whisper` if using a local Whisper API container

Queue:

- `transcribe_whisper`

Use cases:

- CPU Linux
- Apple Silicon
- NVIDIA

Notes:

- The exact runtime can vary by image or env vars.
- The operational model stays the same: start this stack and the machine joins the `transcribe_whisper` queue.

### `docker-compose.worker-qwen.yml`

Services:

- `worker-qwen`
- `asr-qwen`

Queue:

- `transcribe_qwen`

Use cases:

- NVIDIA-first

Notes:

- The worker should be thin and call a sibling Qwen inference service over HTTP.

### `docker-compose.worker-voxtral.yml`

Services:

- `worker-voxtral`
- optionally `asr-voxtral`

Queue:

- `transcribe_voxtral`

Use cases:

- local Voxtral serving if practical
- external Voxtral API if not

Notes:

- This stack should support either local inference or API-backed inference without changing queue routing.

## Generic Worker Environment Variables

Add and standardize these env vars:

- `DEFAULT_TRANSCRIPTION_BACKEND=whisper`
- `TRANSCRIPTION_BACKEND=whisper|qwen|voxtral`
- `CELERY_QUEUES=transcribe_whisper|transcribe_qwen|transcribe_voxtral`
- `ASR_API_URL=http://asr-<backend>:8000/v1`
- `ASR_MODEL=<model-name>`
- `ASR_PROVIDER=<provider-name>`

Keep existing Whisper-specific env vars temporarily for backward compatibility:

- `WHISPER_IMPLEMENTATION`
- `WHISPER_MODEL`
- `ASR_API_URL` for existing `whisper-asr-api` compatibility

## API Routing Rules

Add a new API-level routing input:

- `transcription_backend`

Resolution order:

1. explicit `transcription_backend`
2. system-specific default if added later
3. `DEFAULT_TRANSCRIPTION_BACKEND`

Queue mapping:

- `whisper` -> `transcribe_whisper`
- `qwen` -> `transcribe_qwen`
- `voxtral` -> `transcribe_voxtral`

## Worker Behavior

Each worker should consume exactly one backend queue.

Examples:

- `worker-whisper` consumes `transcribe_whisper`
- `worker-qwen` consumes `transcribe_qwen`
- `worker-voxtral` consumes `transcribe_voxtral`

The worker should know:

- which backend it represents
- which queue it consumes
- where to send inference requests

Preferred inference pattern:

- worker sends audio to a local or remote transcription API
- worker normalizes the response into the existing transcript result shape
- existing post-processing remains unchanged

## Vast Autoscaling Model

Vast should use the same backend-specific worker images or stacks as manual workers.

The autoscaler should scale by backend queue.

Examples:

- backlog on `transcribe_whisper` -> launch more Whisper workers
- backlog on `transcribe_qwen` -> launch more Qwen workers
- backlog on `transcribe_voxtral` -> launch more Voxtral workers

Suggested autoscaler env vars:

- `AUTOSCALE_BACKEND=whisper|qwen|voxtral`
- `AUTOSCALE_QUEUE=transcribe_whisper|transcribe_qwen|transcribe_voxtral`
- `AUTOSCALE_WORKER_IMAGE=<image>`
- `AUTOSCALE_MIN_INSTANCES=<n>`
- `AUTOSCALE_MAX_INSTANCES=<n>`
- `AUTOSCALE_INTERVAL=<seconds>`

Operational model:

- run one autoscaler per backend if needed
- each autoscaler watches one queue
- each autoscaler launches the worker image for that backend

This keeps the logic simple and avoids one giant autoscaler trying to understand every runtime at once.

## File-by-File Implementation Checklist

### `backend/app/worker.py`

Planned changes:

- replace generic GPU queue routing with backend queue routing
- add helper:
  - `get_transcription_queue(backend: str) -> str`
- update `queue_task(...)` to accept `transcription_backend`

Expected queue mapping:

- `whisper` -> `transcribe_whisper`
- `qwen` -> `transcribe_qwen`
- `voxtral` -> `transcribe_voxtral`

### `backend/app/api/routes/calls.py`

Planned changes:

- add optional `transcription_backend`
- default to `whisper`
- pass backend into `worker.queue_task(...)`

### `backend/app/api/routes/tasks.py`

Planned changes:

- add optional `transcription_backend`
- default to `whisper`
- pass backend into `worker.queue_task(...)`

### `backend/app/api/routes/sdrtrunk.py`

Planned changes:

- default ingest jobs to `whisper`
- optionally support future per-system backend overrides

### `backend/app/core/config.py`

Planned changes:

- add:
  - `DEFAULT_TRANSCRIPTION_BACKEND`
  - `TRANSCRIPTION_BACKEND`
  - `ASR_API_URL`
  - `ASR_MODEL`
  - `ASR_PROVIDER`
- keep old Whisper settings temporarily

### `docker/docker-entrypoint.sh`

Planned changes:

- keep worker startup generic
- rely on `CELERY_QUEUES` from compose files
- avoid backend-specific startup logic here unless strictly necessary

### `docker-compose.worker-whisper.yml`

Planned new file:

- defines the Whisper worker stack
- sets:
  - `TRANSCRIPTION_BACKEND=whisper`
  - `CELERY_QUEUES=transcribe_whisper`
  - `ASR_API_URL=http://asr-whisper:8000/v1`

### `docker-compose.worker-qwen.yml`

Planned new file:

- defines the Qwen worker stack
- sets:
  - `TRANSCRIPTION_BACKEND=qwen`
  - `CELERY_QUEUES=transcribe_qwen`
  - `ASR_API_URL=http://asr-qwen:8000/v1`

### `docker-compose.worker-voxtral.yml`

Planned new file:

- defines the Voxtral worker stack
- sets:
  - `TRANSCRIPTION_BACKEND=voxtral`
  - `CELERY_QUEUES=transcribe_voxtral`
  - `ASR_API_URL=http://asr-voxtral:8000/v1` or external API config

### `backend/scripts/autoscale-vast.py`

Planned changes:

- scale by backend queue
- stop assuming one `WHISPER_IMPLEMENTATION` / `WHISPER_MODEL` pair
- use:
  - `AUTOSCALE_BACKEND`
  - `AUTOSCALE_QUEUE`
  - `AUTOSCALE_WORKER_IMAGE`

### `docker-compose.autoscaler.yml`

Planned changes:

- remove Whisper-specific image naming assumptions
- make backend image explicit
- support one autoscaler instance per backend

### `.env.example`

Planned changes:

- add generic backend env vars
- move Whisper-specific env vars under a compatibility section
- update examples to use backend-specific compose files

### `README.md`

Planned changes:

- document setup by worker type
- explain that multiple machines can run the same worker type and share load
- document backend-specific compose files
- document Vast scaling by backend queue

## Suggested Service Names

Worker services:

- `worker-whisper`
- `worker-qwen`
- `worker-voxtral`

Inference services:

- `asr-whisper`
- `asr-qwen`
- `asr-voxtral`

## Suggested User Flows

### Add a Whisper machine

1. copy `.env`
2. select `docker-compose.worker-whisper.yml`
3. run `docker compose up -d`

### Add a Qwen machine

1. copy `.env`
2. select `docker-compose.worker-qwen.yml`
3. run `docker compose up -d`

### Add a Voxtral machine

1. copy `.env`
2. select `docker-compose.worker-voxtral.yml`
3. run `docker compose up -d`

## Recommended Implementation Order

1. add backend queue routing in API and worker
2. add generic backend env/config settings
3. create backend-specific compose files
4. update Vast autoscaler to scale backend queues
5. update docs
6. clean up old Whisper-only assumptions after the new model is working

## End State

After this is implemented:

- any machine can join the pool by starting one backend-specific worker stack
- the stack includes whatever is needed for inference
- the worker consumes the backend queue automatically
- multiple machines can run the same stack and share the load
- Vast autoscaling launches more workers of the same backend type when that queue backs up
