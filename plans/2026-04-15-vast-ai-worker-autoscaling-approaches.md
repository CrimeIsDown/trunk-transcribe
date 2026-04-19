## Vast.ai GPU Worker Autoscaling Approaches

Status: investigated
Date: 2026-04-15

### Goal

Run GPU-backed transcription capacity on Vast.ai with autoscaling, while fitting the current repo architecture:

- one Celery worker per backend queue
- a separate ASR API process for GPU-backed backends
- one autoscaler per backend queue

### Current Repo Shape

The current repo is already close to the desired runtime model:

- the API routes jobs by backend queue in `backend/app/worker.py`
- the worker talks to an OpenAI-compatible ASR HTTP API in `backend/app/whisper/task.py`
- backend-specific compose files already exist for Whisper, Qwen, and Voxtral
- `backend/scripts/autoscale-vast.py` still assumes one Vast instance runs one container with `args=["worker"]`

Important local constraints:

- `backend/scripts/autoscale-vast.py` launches a single container image with `args=["worker"]` and `runtype="args"` (`backend/scripts/autoscale-vast.py:334`)
- the autoscaler sizes `CELERY_CONCURRENCY` as `floor(gpu_ram / vram_required)` (`backend/scripts/autoscale-vast.py:325`)
- the worker no longer runs a local in-process model; it calls `ASR_API_URL` over HTTP (`backend/app/whisper/task.py:129`, `backend/app/whisper/task.py:161`)
- the existing Whisper stack is explicitly two services, `worker-whisper` plus `asr-whisper` (`docker-compose.worker-whisper.yml:2`, `docker-compose.worker-whisper.yml:35`)

That means the current autoscaler model and the current worker runtime model no longer match.

### Vast.ai Constraints That Matter

From current Vast.ai docs:

- Docker instances run one container per instance and Vast does not support Docker-in-Docker
- VM instances do support nested containerization and init systems like `systemd`
- instance creation supports `template_hash_id`, `env`, `onstart`, `args`, and `vm`
- Serverless/Deployments are request-routed HTTP systems with PyWorkers and their own autoscaling model

Practical consequence:

- if we want a GPU worker host to run both `celery worker` and a sibling ASR server on a normal Vast Docker instance, we need one container that supervises both processes
- if we want to keep the repo’s current two-container compose model on Vast, we need a Vast VM, not a normal Docker instance

### Approaches

#### 1. Single-container GPU node on Vast Docker instances

Structure:

- one Vast Docker instance per GPU node
- one custom image per backend
- image starts both:
  - the ASR server
  - the Celery worker
- supervisor can be `s6`, `supervisord`, or a small bash entrypoint with readiness checks

How it maps to this repo:

- keep one autoscaler per backend queue
- keep `post_transcribe` off the GPU hosts
- keep the current worker code mostly unchanged because it already talks to `ASR_API_URL`
- replace backend-specific compose usage on Vast with backend-specific combined images

Pros:

- works with normal Vast Docker instances
- smallest change to the current autoscaler lifecycle model
- fastest path to production
- cheapest operationally because Docker instances have the widest marketplace supply

Cons:

- the “separate ASR API” becomes a separate process, not a separate container
- image build becomes backend-specific and heavier
- process supervision and health signaling need to be added inside the image

Assessment:

- best near-term path
- especially strong for Whisper
- still workable for Qwen and Voxtral if each GPU host should run exactly one active transcription task at a time

#### 2. Vast VM per GPU node running the existing compose stack

Structure:

- one Vast VM per GPU node
- VM boots Docker / Docker Compose
- VM runs the existing backend-specific stack, for example:
  - `docker-compose.worker-whisper.yml`
  - `docker-compose.worker-qwen.yml`
  - `docker-compose.worker-voxtral.yml`

How it maps to this repo:

- preserves the current repo separation most faithfully
- the autoscaler must launch VMs instead of Docker instances
- instance startup must use `vm=true` plus `onstart` or template-based bootstrapping

Pros:

- preserves real container separation between worker and ASR API
- reuses current compose files with fewer semantic changes
- easier to debug because local and Vast layouts are almost identical

Cons:

- slower boot times
- smaller pool of compatible Vast offers
- more moving pieces during startup
- autoscaler logic must learn VM launch behavior and probably longer readiness windows

Assessment:

- best if strict service separation is more important than boot speed and marketplace breadth
- likely the cleanest long-term operational model if Qwen/Voxtral stacks keep growing

#### 3. Vast Serverless / Deployments for the ASR API only

Structure:

- Celery workers run on CPU or ordinary compute
- transcription requests are forwarded to a Vast Serverless endpoint or Deployment
- Vast manages GPU worker autoscaling behind the ASR HTTP endpoint

How it maps to this repo:

- conceptually compatible with the worker’s HTTP-based ASR client
- operationally different from the current queue-based instance autoscaler

Pros:

- Vast owns most GPU autoscaling logic
- a clean “separate ASR API” story
- attractive if the GPU side should become a stateless inference service

Cons:

- this is a larger architecture shift
- Vast Serverless is built around endpoint traffic and PyWorker metrics, not RabbitMQ queue depth
- request auth, readiness, cost control, and cold-start behavior all move into a different platform model
- likely overkill for the current repo unless the ASR service is intentionally being split into a standalone product/service

Assessment:

- worth revisiting later
- not the right first update to `backend/scripts/autoscale-vast.py`

### Recommendation

Recommended order:

1. implement approach 1 for Whisper first
2. generalize the autoscaler around “backend-specific GPU node” rather than “Celery worker owns GPU”
3. decide per backend whether Qwen and Voxtral stay on approach 1 or move to approach 2

Reasoning:

- the worker already uses `ASR_API_URL`, so the repo is already decoupled at the application boundary
- the current blocker is infrastructure packaging, not worker business logic
- Vast Docker instances are the simplest autoscaler target, but they require one container
- a combined image gets the autoscaler working again without forcing a VM migration immediately

If strict container separation on the GPU host is a hard requirement, skip directly to approach 2.

### What `autoscale-vast.py` Should Change

#### 1. Model the launch target as a backend node, not a bare worker

Add env/config like:

- `AUTOSCALE_STACK_MODE=container|vm`
- `AUTOSCALE_TEMPLATE_HASH=...`
- `AUTOSCALE_DISK_GB=...`
- `AUTOSCALE_SEARCH_PARAMS=...`
- `AUTOSCALE_BOOT_TIMEOUT_SECONDS=...`

Why:

- the current script hardcodes image launch details and cannot describe VM boots or template-based launches

#### 2. Stop deriving concurrency from raw VRAM for sidecar/API-backed stacks

Current behavior:

- `CELERY_CONCURRENCY = floor(instance["gpu_ram"] / vram_required)`

Why this is wrong now:

- the GPU is primarily consumed by the ASR server process, not by the Celery worker process
- for Whisper/Qwen/Voxtral sidecar layouts, one GPU node should usually process one transcription at a time unless the specific backend server is benchmarked for safe multi-request concurrency

Recommended default:

- `CELERY_CONCURRENCY=1` for GPU-backed backends
- make it overrideable via `AUTOSCALE_WORKER_CONCURRENCY`

#### 3. Replace the hardcoded `RTX` filter with configurable offer selection

Current behavior:

- available offers are filtered to `num_gpus == 1`
- only `gpu_name` values containing `RTX` are accepted

Problems:

- excludes valid datacenter GPUs like `L4`, `L40S`, `A10`, `A40`, `H100`
- forces one GPU even if a backend might later benefit from a different shape

Recommended:

- let `AUTOSCALE_SEARCH_PARAMS` drive offer selection
- still keep guardrails for:
  - minimum VRAM
  - CUDA compatibility
  - reliability
  - direct ports / networking if needed

#### 4. Prefer Vast templates over raw inline launch bodies

Use `template_hash_id` where possible.

Why:

- Vast templates can hold image, env defaults, ports, launch mode, and provisioning choices
- the autoscaler should mostly choose capacity, not reconstruct the full machine definition every time
- request-level env can still override template values when needed

#### 5. Add backend-specific readiness handling

The current deletion logic treats long `loading` windows as bad after 20 minutes.

That is too naive for model-heavy ASR stacks because first boot may include:

- image pull
- model download
- backend warmup

Recommended:

- separate “instance exists” from “worker ready”
- track:
  - instance status from Vast
  - Celery worker registration
  - optional ASR readiness endpoint
- make loading timeout backend-specific

#### 6. Identify managed instances by label, not only env matching

Current matching is based on `CELERY_BROKER_URL` and `CELERY_QUEUES`.

Recommended:

- add an explicit label such as `tt-whisper-prod`
- use that label plus queue/env checks when listing or deleting instances

This makes cleanup safer when more than one environment shares the same broker.

### Suggested Backend Rollout

#### Whisper

Recommended now:

- combined GPU image containing `speaches` + the Celery worker
- one request at a time per GPU node by default
- repo autoscaler remains the source of truth

#### Qwen

Recommended now:

- start with the same combined-image pattern if the Qwen server is stable enough in one container
- otherwise use the VM approach once the autoscaler supports `vm=true`

#### Voxtral

Recommended now:

- likely the strongest candidate for a VM-based stack if vLLM tuning, caching, or additional sidecars keep growing
- if kept on Docker instances, treat it as one GPU node per active request unless benchmarks prove otherwise

#### API backend

Do not use Vast GPU autoscaling for `api`.

- it is forwarding-only in the current repo
- keep it on ordinary CPU compute

### Implementation Sequence

1. Add a planning abstraction to `autoscale-vast.py` for backend node launch config.
2. Add support for `AUTOSCALE_WORKER_CONCURRENCY` and default GPU-backed backends to `1`.
3. Add support for template-based launches and configurable search filters.
4. Add instance labels and safer instance discovery.
5. Build one combined Whisper GPU image for Vast.
6. Prove the Whisper path end to end.
7. Decide whether Qwen and Voxtral should use combined images or VMs.

### Sources

- Vast Docker execution environment: https://docs.vast.ai/documentation/instances/docker-environment
- Vast instances FAQ: https://docs.vast.ai/documentation/reference/faq/instances
- Vast virtual machines: https://docs.vast.ai/documentation/instances/virtual-machines
- Vast create instance API: https://docs.vast.ai/api-reference/instances/create-instance
- Vast serverless architecture: https://docs.vast.ai/documentation/serverless/architecture
- Vast deployments overview: https://docs.vast.ai/documentation/serverless/deployments
- Vast serverless getting started: https://docs.vast.ai/documentation/serverless/getting-started-with-serverless
