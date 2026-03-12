"""
One-time script: sync all solved UserLevelState rows → CTFd scoreboard.

Run inside the backend container:
    docker compose exec backend python -m app.scripts.sync_solves_to_ctfd

It logs in to CTFd as each user (using a generated session) and submits
the correct flag so CTFd records the solve on its scoreboard.

Since individual user passwords are not stored, we use the CTFd admin API
to look up CTFd user IDs and POST the solve on their behalf via the
/api/v1/submissions admin endpoint.
"""

import logging
import os
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
CTFD_ADMIN_EMAIL = os.getenv("CTFD_ADMIN_EMAIL", "saiprasadrao1234@gmail.com")
CTFD_ADMIN_PASSWORD = os.getenv("CTFD_ADMIN_PASSWORD", "Ssaip@9902")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://ctf_user:ctf_password@db/ctf_db")

TIMEOUT = 10.0


def get_admin_token(client: httpx.Client) -> str:
    """Log in as admin and return the session cookie jar (already set on client)."""
    # Get nonce first
    r = client.get(f"{CTFD_URL}/login", follow_redirects=True)
    import re
    match = re.search(r"['\"]csrfNonce['\"]\s*:\s*['\"]([a-f0-9]+)['\"]", r.text)
    nonce = match.group(1) if match else ""

    r = client.post(
        f"{CTFD_URL}/login",
        data={"name": CTFD_ADMIN_EMAIL, "password": CTFD_ADMIN_PASSWORD, "nonce": nonce},
        follow_redirects=True,
    )
    if "Incorrect" in r.text or r.status_code >= 400:
        logger.error("Admin login failed (HTTP %s)", r.status_code)
        sys.exit(1)
    logger.info("Logged in to CTFd as admin.")
    return nonce


def get_ctfd_user_id(client: httpx.Client, ctf_user_id: int) -> int | None:
    """Look up a CTFd user by their CTFd numeric ID."""
    r = client.get(f"{CTFD_URL}/api/v1/users/{ctf_user_id}")
    if r.status_code == 200:
        return r.json().get("data", {}).get("id")
    return None


def sync():
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Fetch all solved states
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
        import re

        # Admin login
        get_admin_token(client)

        # Get a fresh nonce for API calls
        r = client.get(f"{CTFD_URL}/")
        match = re.search(r"['\"]csrfNonce['\"]\s*:\s*['\"]([a-f0-9]+)['\"]", r.text)
        nonce = match.group(1) if match else ""

        for state, user, level in rows:
            challenge_id = level.ctfd_challenge_id
            if not challenge_id:
                logger.warning(
                    "Level %s has no ctfd_challenge_id — skipping.", level.id
                )
                continue

            ctf_user_id = user.ctf_user_id
            logger.info(
                "Syncing: user=%s (ctf_id=%s) level=%s challenge=%s flag=%s",
                user.username, ctf_user_id, level.id, challenge_id, state.flag_value,
            )

            # Use admin submissions endpoint to record the solve directly
            payload = {
                "challenge_id": challenge_id,
                "user_id": ctf_user_id,
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
                logger.info("  ⚠️  Already recorded in CTFd (skipping): %s", resp.text[:120])
            else:
                logger.warning(
                    "  ❌ Unexpected response HTTP %s: %s",
                    resp.status_code, resp.text[:120],
                )

    db.close()
    logger.info("Sync complete.")


if __name__ == "__main__":
    sync()
