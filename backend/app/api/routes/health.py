from fastapi import APIRouter
from fastapi.responses import JSONResponse


router = APIRouter()


@router.get("/healthz")
def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok"})
