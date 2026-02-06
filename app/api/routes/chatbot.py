from fastapi import APIRouter, HTTPException

from app.ai.scanner_summary_agent import (
    ScannerSummaryRequest,
    ScannerSummaryResponse,
    ScannerSummaryServiceError,
    summarize_scanner_events,
)


router = APIRouter()


@router.post("/chat/transcript-summary", response_model=ScannerSummaryResponse)
async def chat_transcript_summary(
    request: ScannerSummaryRequest,
) -> ScannerSummaryResponse:
    try:
        return await summarize_scanner_events(request)
    except ScannerSummaryServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
