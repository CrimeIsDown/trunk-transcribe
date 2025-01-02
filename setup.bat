git pull
timeout /t 5
uv venv
uv run pip install -U --use-pep517 --extra-index-url https://download.pytorch.org/whl/cu121 git+https://github.com/openai/whisper.git
uv sync

echo Checking that ffmpeg and sox are installed...
ffmpeg
sox
