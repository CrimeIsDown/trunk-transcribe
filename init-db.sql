CREATE TABLE calls (
    id serial PRIMARY KEY,
    raw_metadata jsonb,
    raw_audio_url text,
    raw_transcript jsonb,
    geo jsonb
)
