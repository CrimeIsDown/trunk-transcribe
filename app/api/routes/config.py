import json
import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse


router = APIRouter()


@router.get("/config/{filename}")
def get_config(filename: str) -> JSONResponse:
    if filename not in os.listdir("config"):
        raise HTTPException(status_code=404, detail="Config file not found")

    with open(f"config/{filename}") as config:
        return JSONResponse(json.load(config))
