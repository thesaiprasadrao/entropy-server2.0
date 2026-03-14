"""
Sync all solved UserLevelState rows in Postgres → CTFd scoreboard.

Run inside the backend container:
    docker compose exec backend python -m app.scripts.sync_solves_to_ctfd

Uses the CTFd admin API to:
  1. Look up the CTFd internal user ID by username (because Postgres stores a
     different ctf_user_id that is NOT CTFd's sequential integer PK).
  2. Check whether the solve already exists (to avoid duplicate‑solve 500s).
  3. POST to /api/v1/submissions to record the solve with the correct team_id.
"""

import logging
import os
import re
import sys

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.level import Level
from app.models.user import User
from app.models.user_level_state import UserLevelState

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

CTFD_URL = os.getenv("CTFD_INTERNAL_URL", "http://ctfd:8000")
CTFD_ADMIN_EMAIL = os.getenv("CTFD_ADMIN_EMAIL") or ""
CTFD_ADMIN_PASSWORD = os.getenv("CTFD_ADMIN_PASSWORD") or ""
DATABASE_URL = os.getenv("DATABASE_URL") or ""

if not CTFD_ADMIN_EMAIL or not CTFD_ADMIN_PASSWORD or not DATABASE_URL:
    logger.error(
        "CTFD_ADMIN_EMAIL, CTFD_ADMIN_PASSWORD and DATABASE_URL must be set in environment"
    )
    sys.exit(1)

TIMEOUT = 10.0


def admin_login(client: httpx.Client) -> str:
    """Log in as admin; returns fresh CSRF nonce. Session cookies stored on client."""
    r = client.get(f"{CTFD_URL}/login", follow_redirects=True)
    match = re.search(r"['\"]csrfNonce['\"]\s*:\s*['\"]([a-f0-9]+)['\"]", r.text)
    nonce = match.group(1) if match else ""

    r = client.post(
        f"{CTFD_URL}/login",
        data={
            "name": CTFD_ADMIN_EMAIL,
            "password": CTFD_ADMIN_PASSWORD,
            "nonce": nonce,
        },
        follow_redirects=True,
    )
    if r.status_code >= 400 or "Incorrect" in r.text:
        logger.error("Admin login failed (HTTP %s)", r.status_code)
        sys.exit(1)
    logger.info("Logged in to CTFd as admin.")

    # Grab a fresh nonce from the home page for use in API calls
    r = client.get(f"{CTFD_URL}/")
    match = re.search(r"['\"]csrfNonce['\"]\s*:\s*['\"]([a-f0-9]+)['\"]", r.text)
    return match.group(1) if match else ""


def get_ctfd_user_id_by_name(client: httpx.Client, username: str) -> int | None:
    """
    Look up CTFd's internal sequential user ID by username.
    Postgres stores ctf_user_id which is NOT the same as CTFd's integer PK.
    """
    r = client.get(f"{CTFD_URL}/api/v1/users", params={"q": username, "field": "name"})
    if r.status_code != 200:
        return None
    results = r.json().get("data", [])
    for u in results:
        if u.get("name", "").lower() == username.lower():
            return u["id"]
    return None


def solve_already_in_ctfd(
    client: httpx.Client, ctfd_user_id: int, challenge_id: int
) -> bool:
    """Return True if CTFd already has a correct solve for this user+challenge."""
    r = client.get(
        f"{CTFD_URL}/api/v1/submissions",
        params={
            "user_id": ctfd_user_id,
            "challenge_id": challenge_id,
            "type": "correct",
        },
    )
    if r.status_code != 200:
        return False
    return len(r.json().get("data", [])) > 0


def sync():
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Fetch all solved states joined with user and level
    rows = (
        db.query(UserLevelState, User, Level)
        .join(User, User.id == UserLevelState.user_id)
        .join(Level, Level.id == UserLevelState.level_id)
        .filter(UserLevelState.solved == True)
        .all()
    )

    if not rows:
        logger.info("No solved states found in local DB. Nothing to sync.")
        return

    logger.info("Found %d solved state(s) to sync to CTFd.", len(rows))

    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
        nonce = admin_login(client)

        for state, user, level in rows:
            challenge_id = level.ctfd_challenge_id
            if not challenge_id:
                logger.warning(
                    "Level %s has no ctfd_challenge_id — skipping.", level.id
                )
                continue

            # --- Look up the real CTFd user ID by username ---
            ctfd_user_id = get_ctfd_user_id_by_name(client, user.username)
            if ctfd_user_id is None:
                logger.warning(
                    "  ⚠️  User '%s' not found in CTFd — skipping (they may not have registered yet).",
                    user.username,
                )
                continue

            logger.info(
                "Syncing: user=%s (ctfd_id=%s) level=%s challenge=%s",
                user.username,
                ctfd_user_id,
                level.id,
                challenge_id,
            )

            # --- Skip if already recorded in CTFd ---
            if solve_already_in_ctfd(client, ctfd_user_id, challenge_id):
                logger.info("  ⏭️  Already in CTFd scoreboard — skipping.")
                continue

            # --- POST the solve via admin submissions endpoint ---
            payload = {
                "challenge_id": challenge_id,
                "user_id": ctfd_user_id,
                "type": "correct",
                "provided": state.flag_value,
            }
            headers = {"CSRF-Token": nonce, "Content-Type": "application/json"}
            resp = client.post(
                f"{CTFD_URL}/api/v1/submissions",
                json=payload,
                headers=headers,
            )

            if resp.status_code in (200, 201):
                logger.info("  ✅ Synced successfully.")
            elif resp.status_code == 400:
                logger.info(
                    "  ⏭️  Already recorded in CTFd (400 dupe): %s", resp.text[:120]
                )
            else:
                logger.warning(
                    "  ❌ Unexpected HTTP %s: %s",
                    resp.status_code,
                    resp.text[:200],
                )

    db.close()
    logger.info("Sync complete.")


if __name__ == "__main__":
    sync()
