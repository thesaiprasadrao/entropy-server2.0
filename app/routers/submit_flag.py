import logging
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.level import Level

logger = logging.getLogger(__name__)

router = APIRouter(tags=["flags"])

CTFD_INTERNAL_URL = "http://ctfd:8000"
REQUEST_TIMEOUT = 5.0  # seconds


class MeResponse(BaseModel):
    username: str
    name: str


class SubmitFlagRequest(BaseModel):
    flag: str
    level_id: int  # Backend resolves this to ctfd_challenge_id via DB


class SubmitFlagResponse(BaseModel):
    status: str   # "correct" | "incorrect"
    message: str


@router.get("/me", response_model=MeResponse)
def get_me(request: Request) -> MeResponse:
    """Fetch the CTFd-authenticated user's info from the session cookie."""
    cookies = dict(request.cookies)
    if not cookies:
        raise HTTPException(status_code=401, detail="Not logged in to CTFd.")

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            resp = client.get(
                f"{CTFD_INTERNAL_URL}/api/v1/users/me",
                cookies=cookies,
            )
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="CTFd timed out.")
    except (httpx.RequestError, httpx.HTTPStatusError):
        raise HTTPException(status_code=401, detail="Not logged in to CTFd.")

    user_data = data.get("data", {})
    # CTFd returns 200 even for anonymous users when not logged in — check id
    if not user_data.get("id"):
        raise HTTPException(status_code=401, detail="Not logged in to CTFd.")

    return MeResponse(
        username=user_data.get("name", ""),
        name=user_data.get("name", ""),
    )


def get_ctfd_nonce(cookies: dict) -> str:
    """Fetch a fresh CSRF nonce from CTFd's main page for the given session."""
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(f"{CTFD_INTERNAL_URL}/", cookies=cookies)
        # CTFd embeds: window.init = {'csrfNonce': "abc123...", ...}
        match = re.search(r"""['"]csrfNonce['"]\s*:\s*"([a-f0-9]+)""", resp.text)
        if match:
            return match.group(1)
        logger.warning("Could not extract csrfNonce from CTFd HTML")
    except Exception as exc:
        logger.warning("Failed to fetch CTFd nonce: %s", exc)
    return ""


@router.post("/submit_flag", response_model=SubmitFlagResponse)
def submit_flag(
    body: SubmitFlagRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> SubmitFlagResponse:
    # 1. Resolve level_id → ctfd_challenge_id from DB
    level = db.query(Level).filter(Level.id == body.level_id).first()
    if level is None:
        raise HTTPException(status_code=404, detail=f"Level {body.level_id} not found.")

    if not hasattr(level, "ctfd_challenge_id") or level.ctfd_challenge_id is None:
        raise HTTPException(
            status_code=503,
            detail="This level is not yet linked to a CTFd challenge. Check back soon.",
        )

    challenge_id = level.ctfd_challenge_id

    # 2. Forward ALL incoming cookies so CTFd session authentication works
    cookies = dict(request.cookies)
    if not cookies:
        logger.warning("submit_flag called with no cookies — user may not be logged into CTFd")
        raise HTTPException(
            status_code=401,
            detail="No CTFd session found. Please log in first.",
        )

    # 3. Fetch CSRF nonce — CTFd requires this on every POST to its API
    nonce = get_ctfd_nonce(cookies)

    payload = {
        "challenge_id": challenge_id,
        "submission": body.flag,
    }
    if nonce:
        payload["nonce"] = nonce

    logger.info(
        "Forwarding flag submission: level_id=%s challenge_id=%s",
        body.level_id,
        challenge_id,
    )

    # 3. Call CTFd API with timeout and full error handling
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            resp = client.post(
                f"{CTFD_INTERNAL_URL}/api/v1/challenges/attempt",
                json=payload,
                cookies=cookies,
            )
        resp.raise_for_status()
        data = resp.json()

    except httpx.TimeoutException:
        logger.error("CTFd request timed out after %.1fs", REQUEST_TIMEOUT)
        raise HTTPException(status_code=504, detail="CTFd validation timed out. Try again.")

    except httpx.RequestError as exc:
        logger.error("CTFd network error: %s", exc)
        raise HTTPException(status_code=502, detail="Could not reach CTFd. Try again.")

    except httpx.HTTPStatusError as exc:
        logger.error(
            "CTFd returned HTTP %s: %s",
            exc.response.status_code,
            exc.response.text[:200],
        )
        if exc.response.status_code in (401, 403):
            raise HTTPException(
                status_code=401,
                detail="CTFd rejected your session. Please log in at /ctfd/ again.",
            )
        raise HTTPException(status_code=502, detail="CTFd rejected the request.")

    # 4. Parse CTFd response
    # CTFd shape: { "success": true, "data": { "status": "correct"|"incorrect", "message": "..." } }
    ctfd_data = data.get("data", {})
    ctfd_status = ctfd_data.get("status", "incorrect")

    logger.info(
        "CTFd result for level_id=%s challenge_id=%s: %s",
        body.level_id,
        challenge_id,
        ctfd_status,
    )

    return SubmitFlagResponse(
        status=ctfd_status,
        message="Flag accepted! Level solved." if ctfd_status == "correct" else "Incorrect flag. Keep trying!",
    )
