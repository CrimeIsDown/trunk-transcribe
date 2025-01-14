from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlmodel import Session
from app.api.depends import get_db
from app.models import models


router = APIRouter()


@router.get("/talkgroups")
def talkgroups(db: Session = Depends(get_db)) -> JSONResponse:
    tgs = models.get_talkgroups(db)
    return JSONResponse({"talkgroups": tgs})
