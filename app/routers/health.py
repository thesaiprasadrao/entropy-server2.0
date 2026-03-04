from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health_check():
    """Pure availability probe — no DB call, always fast."""
    return {"status": "ok"}
