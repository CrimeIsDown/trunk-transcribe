git pull
timeout /t 5
call .\.venv\Scripts\activate
pip install poetry
pip install --use-pep517 --extra-index-url https://download.pytorch.org/whl/cu117 git+https://github.com/openai/whisper.git
poetry install

echo Checking that ffmpeg and sox are installed...
ffmpeg
sox
