# Architecture

This document complements the top-level README with compact Mermaid diagrams for the deployed system and the transcription provider stack.

## Runtime Topology

```mermaid
flowchart LR
    TR[trunk-recorder<br/>transcribe.sh]
    API[API]
    RMQ[(RabbitMQ)]

    subgraph BW[Backend queues and workers]
        QW[transcribe_whisper]
        QQ[transcribe_qwen]
        QV[transcribe_voxtral]
        WP[worker-whisper]
        WQ[worker-qwen]
        WV[worker-voxtral]
    end

    subgraph ASR[Transcript providers]
        SW[Whisper ASR server]
        SQ[Qwen ASR server]
        SV[Voxtral vLLM server]
    end

    PQ[post_transcribe]
    POST[post worker]
    DB[(Postgres)]
    SEARCH[(Meilisearch / Typesense)]
    UI[Frontend + chat-ui]
    NOTIFY[Notifications]
    FLOWER[Flower]
    AUTO[autoscale-vast]

    TR --> API --> RMQ
    RMQ --> QW --> WP --> SW
    RMQ --> QQ --> WQ --> SQ
    RMQ --> QV --> WV --> SV

    WP --> RMQ
    WQ --> RMQ
    WV --> RMQ
    RMQ --> PQ --> POST

    POST --> DB
    POST --> SEARCH
    POST --> NOTIFY
    UI --> API
    UI --> SEARCH
    FLOWER --> RMQ
    AUTO --> RMQ
    AUTO -. scales backend workers .-> BW
```

## Transcript Providers And Models

```mermaid
flowchart TB
    subgraph Whisper[Whisper backend]
        WQ[transcribe_whisper] --> WW[worker-whisper]
        WW --> WS[whisper-asr-webservice<br/>default model: small.en]
        WW -. optional .-> WO[OpenAI API<br/>whisper-1]
        WW -. optional .-> WD[DeepInfra API<br/>openai/whisper-large-v3-turbo]
        WW -. optional .-> WG[Deepgram API<br/>nova-2]
    end

    subgraph Qwen[Qwen backend]
        QQ[transcribe_qwen] --> QW[worker-qwen]
        QW --> QS[qwen3-asr-server<br/>default model: qwen3-asr-p25]
    end

    subgraph Voxtral[Voxtral backend]
        VQ[transcribe_voxtral] --> VW[worker-voxtral]
        VW --> VS[vLLM OpenAI server<br/>default model: Voxtral-Mini-4B-Realtime-2602]
    end
```

## Default Backend Stacks

| Backend | Queue | Worker compose | Provider server | Default model |
| --- | --- | --- | --- | --- |
| Whisper | `transcribe_whisper` | `docker-compose.worker-whisper.yml` | `onerahmet/openai-whisper-asr-webservice` | `small.en` |
| Qwen | `transcribe_qwen` | `docker-compose.worker-qwen.yml` | `ghcr.io/trunk-reporter/qwen3-asr-server:gpu` | `qwen3-asr-p25` |
| Voxtral | `transcribe_voxtral` | `docker-compose.worker-voxtral.yml` | `vllm/vllm-openai:latest` | `mistralai/Voxtral-Mini-4B-Realtime-2602` |

## Notes

- Each machine should run one backend-specific worker stack plus any shared infrastructure it needs to reach RabbitMQ and the API.
- The backend worker normalizes transcripts before handing them to the shared `post_transcribe` flow.
- `autoscale-vast` should manage one backend queue per autoscaler instance.
- Flower observes queue and worker state; it is not on the transcript data path.
