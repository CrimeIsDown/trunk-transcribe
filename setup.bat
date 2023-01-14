git pull
call .\.venv\Scripts\activate
pip install --extra-index-url https://download.pytorch.org/whl/cu117 git+https://github.com/openai/whisper.git
pip install -r requirements.txt
