# trunk-transcribe Backend

The Python service now lives under `backend/`, following the same backend/frontend separation used by the FastAPI full-stack template.

## Development

From the repository root:

```bash
uv sync --directory backend
./make.sh lint
./make.sh test
```

Direct backend commands can also run with `uv` scoped to `backend/`:

```bash
uv run --directory backend python -m pytest
uv run --directory backend mypy app
uv run --directory backend ruff check app tests
```

## Layout

- `backend/app/`: FastAPI app, workers, domain modules, and Alembic environment
- `backend/scripts/`: operational and developer entrypoint scripts
- `backend/tests/`: backend test suite and test data
- `backend/alembic.ini`: Alembic configuration for the backend service
