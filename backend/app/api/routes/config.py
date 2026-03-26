import json
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse


router = APIRouter()

CONFIG_DIR = Path(__file__).parent.parent.parent.parent.parent / "config"


@router.get("/config/{filename}")
def get_config(filename: str) -> JSONResponse:
    if filename not in os.listdir(CONFIG_DIR):
        raise HTTPException(status_code=404, detail="Config file not found")

    with open(CONFIG_DIR / filename) as config:
        return JSONResponse(json.load(config))
