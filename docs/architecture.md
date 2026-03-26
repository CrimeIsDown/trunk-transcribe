# Architecture

This document complements the top-level README with a compact system diagram and a backend reference table.

## Diagram Conventions

- One diagram should answer one question. The main diagram below focuses on runtime flow, not every container detail.
- Components are grouped by responsibility so the reader can scan left to right: ingest, routing, backend execution, post-processing, and consumers.
- Provider nodes include the default model where that adds useful context.
- Operational components such as Flower and the autoscaler are shown off the main transcript path.

## System Flow

```mermaid
flowchart LR
    subgraph INGEST[Ingest]
        TR[trunk-recorder<br/>transcribe.sh]
        API[API]
    end

    subgraph QUEUES[RabbitMQ queues]
        QW[transcribe_whisper]
        QA[transcribe_api]
        QQ[transcribe_qwen]
        QV[transcribe_voxtral]
        QP[post_transcribe]
    end

    subgraph EXEC[Backend workers]
        WP[worker-whisper]
        WA[worker-api]
        WQ[worker-qwen]
        WV[worker-voxtral]
    end

    subgraph PROVIDERS[Transcript providers]
        PW[Speaches Whisper server<br/>default model: Systran/faster-distil-whisper-small.en]
        PA[Vendor APIs<br/>OpenAI: whisper-1<br/>DeepInfra: whisper-large-v3-turbo]
        PQW[Qwen server<br/>default model: qwen3-asr-p25]
        PV[Voxtral vLLM<br/>default model: Voxtral-Mini-4B-Realtime-2602]
    end

    subgraph POSTPROC[Post-processing]
        POST[post worker]
        DB[(Postgres)]
        SEARCH[(Meilisearch / Typesense)]
        NOTIFY[Notifications]
    end

    subgraph OPS[Ops and consumers]
        UI[Frontend + chat-ui]
        FLOWER[Flower]
        AUTO[autoscale-vast]
    end

    TR -->|upload call + metadata| API
    API -->|enqueue by transcription_backend| QW
    API -->|enqueue by transcription_backend| QA
    API -->|enqueue by transcription_backend| QQ
    API -->|enqueue by transcription_backend| QV

    QW --> WP --> PW -->|normalized transcript| QP
    QA --> WA --> PA -->|normalized transcript| QP
    QQ --> WQ --> PQW -->|normalized transcript| QP
    QV --> WV --> PV -->|normalized transcript| QP

    QP --> POST
    POST --> DB
    POST --> SEARCH
    POST --> NOTIFY

    UI --> API
    UI --> SEARCH
    FLOWER -. monitors .-> QUEUES
    AUTO -. scales GPU-backed backend workers .-> EXEC
```

## Default Backend Stacks

| Backend | Queue | Worker compose | Provider server | Default model |
| --- | --- | --- | --- | --- |
| Whisper | `transcribe_whisper` | `docker-compose.worker-whisper.yml` | `ghcr.io/speaches-ai/speaches` | `Systran/faster-distil-whisper-small.en` |
| API | `transcribe_api` | `docker-compose.worker-api.yml` | OpenAI, Deepgram, or DeepInfra | Provider-specific |
| Qwen | `transcribe_qwen` | `docker-compose.worker-qwen.yml` | `ghcr.io/trunk-reporter/qwen3-asr-server:gpu` | `qwen3-asr-p25` |
| Voxtral | `transcribe_voxtral` | `docker-compose.worker-voxtral.yml` | `vllm/vllm-openai:latest` | `mistralai/Voxtral-Mini-4B-Realtime-2602` |

## Notes

- Each machine should run one backend-specific worker stack plus any shared infrastructure it needs to reach RabbitMQ and the API.
- The backend worker normalizes transcripts before handing them to the shared `post_transcribe` flow.
- The `api` backend is forwarding-only and does not need GPU capacity.
- `autoscale-vast` should manage one backend queue per autoscaler instance.
- Flower observes queue and worker state; it is not on the transcript data path.
