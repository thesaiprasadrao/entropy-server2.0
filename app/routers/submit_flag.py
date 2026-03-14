import hmac
import logging
import os
import re
from functools import lru_cache

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.level import Level
from app.models.user import User
from app.models.user_level_state import UserLevelState
from app.middleware.auth import verify_ctfd_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["flags"])

CTFD_INTERNAL_URL = "http://ctfd:8000"
REQUEST_TIMEOUT = 5.0  # seconds
CTFD_ADMIN_EMAIL = os.getenv("CTFD_ADMIN_EMAIL", "")
CTFD_ADMIN_PASSWORD = os.getenv("CTFD_ADMIN_PASSWORD", "")


@lru_cache(maxsize=1)
def _get_admin_session_cookies() -> dict:
    """Log in to CTFd as admin and return the session cookie dict (cached)."""
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            r = client.get(f"{CTFD_INTERNAL_URL}/login")
            match = re.search(
                r"['\"]csrfNonce['\"]\s*:\s*['\"]([a-f0-9]+)['\"]", r.text
            )
            nonce = match.group(1) if match else ""
            r = client.post(
                f"{CTFD_INTERNAL_URL}/login",
                data={
                    "name": CTFD_ADMIN_EMAIL,
                    "password": CTFD_ADMIN_PASSWORD,
                    "nonce": nonce,
                },
                follow_redirects=True,
            )
            if r.status_code >= 400 or "Incorrect" in r.text:
                logger.warning("CTFd admin login failed — scoreboard sync disabled.")
                return {}
            return dict(client.cookies)
    except Exception as exc:
        logger.warning("CTFd admin login error: %s", exc)
        return {}


def _get_admin_nonce(cookies: dict) -> str:
    """Fetch a fresh CSRF nonce from CTFd using admin session cookies."""
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            r = client.get(f"{CTFD_INTERNAL_URL}/", cookies=cookies)
            match = re.search(
                r"['\"]csrfNonce['\"]\s*:\s*['\"]([a-f0-9]+)['\"]", r.text
            )
            if match:
                return match.group(1)
    except Exception as exc:
        logger.warning("Failed to fetch admin nonce: %s", exc)
    return ""


def _lookup_ctfd_user_id_by_name(username: str, cookies: dict) -> int | None:
    """Look up CTFd's real sequential integer user ID by username.
    Postgres stores a different ctf_user_id that is NOT CTFd's PK.
    """
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(
                f"{CTFD_INTERNAL_URL}/api/v1/users",
                params={"q": username, "field": "name"},
                cookies=cookies,
            )
        if resp.status_code == 200:
            for u in resp.json().get("data", []):
                if u.get("name", "").lower() == username.lower():
                    return u["id"]
    except Exception as exc:
        logger.warning("CTFd user lookup error for '%s': %s", username, exc)
    return None


def sync_solve_to_ctfd_admin(username: str, challenge_id: int, flag_value: str) -> None:
    """Submit a correct solve to CTFd via the admin /api/v1/submissions endpoint.
    Looks up CTFd's real sequential user ID by username so team_id is recorded correctly.
    """
    if not CTFD_ADMIN_EMAIL or not CTFD_ADMIN_PASSWORD:
        logger.warning("CTFD_ADMIN_EMAIL/PASSWORD not set — skipping admin sync.")
        return
    try:
        # Get cached admin session (re-login if cookies are empty)
        cookies = _get_admin_session_cookies()
        if not cookies:
            _get_admin_session_cookies.cache_clear()
            cookies = _get_admin_session_cookies()
        if not cookies:
            logger.warning("Could not obtain admin session for CTFd sync.")
            return

        # Look up CTFd's real sequential user ID (NOT Postgres ctf_user_id)
        ctfd_real_id = _lookup_ctfd_user_id_by_name(username, cookies)
        if ctfd_real_id is None:
            logger.warning(
                "CTFd user '%s' not found — skipping scoreboard sync.", username
            )
            return

        nonce = _get_admin_nonce(cookies)
        payload = {
            "challenge_id": challenge_id,
            "user_id": ctfd_real_id,
            "type": "correct",
            "provided": flag_value,
        }
        headers = {"CSRF-Token": nonce, "Accept": "application/json"}
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            resp = client.post(
                f"{CTFD_INTERNAL_URL}/api/v1/submissions",
                json=payload,
                cookies=cookies,
                headers=headers,
            )
        if resp.status_code in (200, 201):
            logger.info(
                "CTFd admin sync OK: user=%s (ctfd_id=%s) challenge_id=%s",
                username,
                ctfd_real_id,
                challenge_id,
            )
        elif resp.status_code == 400:
            logger.info(
                "CTFd admin sync: already recorded (user=%s challenge_id=%s)",
                username,
                challenge_id,
            )
        else:
            logger.warning(
                "CTFd admin sync unexpected HTTP %s: %s",
                resp.status_code,
                resp.text[:200],
            )
            # If 401/403 the cached session expired — clear and retry next time
            if resp.status_code in (401, 403):
                _get_admin_session_cookies.cache_clear()
    except Exception as exc:
        logger.warning("CTFd admin sync error: %s", exc)


class MeResponse(BaseModel):
    username: str
    name: str


class SubmitFlagRequest(BaseModel):
    flag: str
    level_id: int
    username: str = ""  # passed from frontend; used to look up user's assigned flag


class SubmitFlagResponse(BaseModel):
    status: str  # "correct" | "incorrect"
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
        # CTFd embeds: window.init = {'csrfNonce': 'abc123...', ...}
        match = re.search(r"['\"]csrfNonce['\"]\s*:\s*['\"]([a-f0-9]+)['\"]", resp.text)
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
    auth_username: str = Depends(verify_ctfd_session),
) -> SubmitFlagResponse:
    # Enforce authenticated identity — ignore body.username, use verified session
    username = auth_username
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

    cookies = dict(request.cookies)

    # 2b. Validate flag locally using authenticated username from session.
    # Our PostgreSQL DB is the source of truth for each user's assigned flag.
    # We return the result directly here, bypassing CTFd's submission API
    # (CTFd's cookie handling is unreliable across browsers/origins).
    user = db.query(User).filter(User.username == username).first()
    if user:
        state = (
            db.query(UserLevelState)
            .filter(
                UserLevelState.user_id == user.id,
                UserLevelState.level_id == body.level_id,
            )
            .first()
        )
        if state and state.flag_value:
            flag_correct = hmac.compare_digest(
                body.flag.strip().lower(),
                state.flag_value.strip().lower(),
            )
            if not flag_correct:
                logger.info(
                    "Flag INCORRECT for user=%s level_id=%s", username, body.level_id
                )
                return SubmitFlagResponse(
                    status="incorrect",
                    message="Incorrect flag. Keep trying!",
                )
            # Flag is correct — mark solved in our DB
            already_solved = state.solved
            if not already_solved:
                state.solved = True
                db.commit()
            logger.info("Flag CORRECT for user=%s level_id=%s", username, body.level_id)

            # Also forward to CTFd via admin API so the scoreboard registers
            # the solve with the correct team_id (cookie-based submission loses
            # team association, causing team names not to appear on the scoreboard).
            if not already_solved:
                sync_solve_to_ctfd_admin(
                    username=user.username,
                    challenge_id=challenge_id,
                    flag_value=state.flag_value,
                )

            return SubmitFlagResponse(
                status="correct",
                message="Flag accepted! Level solved.",
            )

    challenge_id = level.ctfd_challenge_id

    cookies = dict(request.cookies)
    if not cookies:
        logger.warning("submit_flag called with no cookies — user not logged into CTFd")
        raise HTTPException(
            status_code=401,
            detail="You need to be logged in to submit a flag. Please log in at the main page.",
        )

    # 2b. Validate flag locally using username from request body.
    # Our PostgreSQL DB is the source of truth for each user's assigned flag.
    # We return the result directly here, bypassing CTFd's submission API
    # (CTFd's cookie handling is unreliable across browsers/origins).
    if body.username:
        user = db.query(User).filter(User.username == body.username).first()
        if user:
            state = (
                db.query(UserLevelState)
                .filter(
                    UserLevelState.user_id == user.id,
                    UserLevelState.level_id == body.level_id,
                )
                .first()
            )
            if state and state.flag_value:
                flag_correct = hmac.compare_digest(
                    body.flag.strip().lower(),
                    state.flag_value.strip().lower(),
                )
                if not flag_correct:
                    logger.info(
                        "Flag INCORRECT for user=%s level_id=%s",
                        body.username,
                        body.level_id,
                    )
                    return SubmitFlagResponse(
                        status="incorrect",
                        message="Incorrect flag. Keep trying!",
                    )
                # Flag is correct — mark solved in our DB
                already_solved = state.solved
                if not already_solved:
                    state.solved = True
                    db.commit()
                logger.info(
                    "Flag CORRECT for user=%s level_id=%s", body.username, body.level_id
                )

                # Also forward to CTFd via admin API so the scoreboard registers
                # the solve with the correct team_id (cookie-based submission loses
                # team association, causing team names not to appear on the scoreboard).
                if not already_solved:
                    sync_solve_to_ctfd_admin(
                        username=user.username,
                        challenge_id=challenge_id,
                        flag_value=state.flag_value,
                    )

                return SubmitFlagResponse(
                    status="correct",
                    message="Flag accepted! Level solved.",
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
    headers = {"Accept": "application/json"}
    if nonce:
        headers["CSRF-Token"] = nonce

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            resp = client.post(
                f"{CTFD_INTERNAL_URL}/api/v1/challenges/attempt",
                json=payload,
                cookies=cookies,
                headers=headers,
            )
        resp.raise_for_status()
        data = resp.json()

    except httpx.TimeoutException:
        logger.error("CTFd request timed out after %.1fs", REQUEST_TIMEOUT)
        raise HTTPException(
            status_code=504, detail="CTFd validation timed out. Try again."
        )

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
                detail="Your session has expired. Please log in again at the main page.",
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
        message="Flag accepted! Level solved."
        if ctfd_status == "correct"
        else "Incorrect flag. Keep trying!",
    )
