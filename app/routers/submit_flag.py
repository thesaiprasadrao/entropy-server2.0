import hmac
import logging
import os
import re
import threading
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.level import Level
from app.models.user import User
from app.models.user_level_state import UserLevelState
from app.middleware.auth import verify_ctfd_session
from app.middleware.rate_limiter import check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(tags=["flags"])

CTFD_INTERNAL_URL = "http://ctfd:8000"
REQUEST_TIMEOUT = 5.0  # seconds
CTFD_ADMIN_EMAIL = os.getenv("CTFD_ADMIN_EMAIL", "")
CTFD_ADMIN_PASSWORD = os.getenv("CTFD_ADMIN_PASSWORD", "")

# TTL-based admin session cache — refresh every 30 minutes instead of
# caching forever with lru_cache (which never retries on failure).
_admin_session_lock = threading.Lock()
_admin_session_cookies: dict = {}
_admin_session_expires: float = 0.0
_ADMIN_SESSION_TTL = 1800  # 30 minutes


def _get_admin_session_cookies() -> dict:
    """Return cached CTFd admin session cookies, refreshing if expired."""
    global _admin_session_cookies, _admin_session_expires
    now = time.monotonic()
    with _admin_session_lock:
        if _admin_session_cookies and now < _admin_session_expires:
            return _admin_session_cookies

    # Outside lock: do the actual HTTP login (slow path)
    cookies = _do_admin_login()
    with _admin_session_lock:
        _admin_session_cookies = cookies
        # If login failed, retry sooner (60s) so transient errors self-heal
        _admin_session_expires = now + (_ADMIN_SESSION_TTL if cookies else 60)
    return cookies


def _do_admin_login() -> dict:
    """Perform the CTFd admin login and return session cookies, or {} on failure."""
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
    global _admin_session_expires
    if not CTFD_ADMIN_EMAIL or not CTFD_ADMIN_PASSWORD:
        logger.warning("CTFD_ADMIN_EMAIL/PASSWORD not set — skipping admin sync.")
        return
    try:
        # Get cached admin session (re-login if expired or empty)
        cookies = _get_admin_session_cookies()
        if not cookies:
            # Force immediate re-login on next call
            with _admin_session_lock:
                _admin_session_expires = 0.0
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
            # If 401/403 the cached session expired — force re-login next call
            if resp.status_code in (401, 403):
                with _admin_session_lock:
                    _admin_session_expires = 0.0
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

    # Rate limit by IP (same strategy as /chat).
    # X-Real-IP is set by Nginx (proxy_set_header X-Real-IP $remote_addr) and
    # overwrites any client-supplied header, so it is safe to trust here.
    client_ip = request.headers.get("X-Real-IP") or (
        request.client.host if request.client else "unknown"
    )
    check_rate_limit(client_ip)

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

    # User not found in local DB — raise 403 rather than falling through to untrusted paths
    raise HTTPException(
        status_code=403,
        detail="Open the level first via POST /levels/{level_id}/open",
    )
