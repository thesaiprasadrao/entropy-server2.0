import json
import logging
import os
import re
import sys
from pathlib import Path

import httpx
import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

LEVELS_FILE = Path(__file__).parent.parent.parent / "levels.yaml"
# CTFd is available at this internal URL inside the docker network
CTFD_URL = "http://ctfd:8000"


def load_env() -> dict:
    env_file = Path(__file__).parent.parent.parent / ".env"
    env = {}
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip("'\"")
    return env


def load_levels() -> list[dict]:
    if not LEVELS_FILE.exists():
        logger.error(f"levels.yaml not found at {LEVELS_FILE}")
        sys.exit(1)
    with open(LEVELS_FILE, "r") as f:
        data = yaml.safe_load(f)
    return data.get("levels", [])


def admin_login(client: httpx.Client, env: dict) -> bool:
    """Logs into CTFd using credentials from .env to establish an admin session."""
    logger.info("Fetching login nonce...")
    try:
        r = client.get(f"{CTFD_URL}/login")
    except httpx.ConnectError:
        logger.error(f"Could not connect to CTFd at {CTFD_URL}. Is it running?")
        sys.exit(1)

    nonce_match = re.search(r"['\"]csrfNonce['\"]\s*:\s*\"([a-f0-9]+)\"", r.text)
    if not nonce_match:
        if "setup" in str(r.url):
            logger.error("CTFd has not been set up yet! Please visit http://localhost/ in your browser and complete the initial setup wizard first.")
            sys.exit(1)
        nonce = ""
    else:
        nonce = nonce_match.group(1)

    username = env.get("CTFD_ADMIN_EMAIL")
    password = env.get("CTFD_ADMIN_PASSWORD")
    if not username or not password:
        logger.error("CTFD_ADMIN_EMAIL or CTFD_ADMIN_PASSWORD missing from .env file!")
        logger.error("Please add the admin credentials you created during the CTFd setup to the .env file.")
        sys.exit(1)

    logger.info(f"Logging into CTFd as {username}...")
    r = client.post(
        f"{CTFD_URL}/login",
        data={
            "name": username,
            "password": password,
            "_submit": "Submit",
            "nonce": nonce,
        },
    )

    if "incorrect" in r.text.lower() or "invalid" in r.text.lower():
        logger.error(f"Login failed! Check your CTFd admin credentials in the .env file.")
        sys.exit(1)

    check = client.get(
        f"{CTFD_URL}/api/v1/challenges",
        headers={"Accept": "application/json"}
    )
    if check.status_code == 403:
        logger.error("Login succeeded but user is not an Admin.")
        sys.exit(1)

    logger.info("✅ Admin session established.")
    
    # Fetch an HTML page to extract the CSRF nonce for subsequent POSTs
    admin_page = client.get(f"{CTFD_URL}/admin/challenges")
    nonce_match = re.search(r"['\"]csrfNonce['\"]\s*:\s*['\"]([a-f0-9]+)['\"]", admin_page.text)
    if nonce_match:
        client.headers.update({"CSRF-Token": nonce_match.group(1)})
    else:
        logger.warning("Could not extract admin CSRF nonce. POST requests might fail.")
        
    return True


def sync_challenges():
    env = load_env()
    levels = load_levels()

    with httpx.Client(follow_redirects=True, timeout=10.0) as client:
        # 1. Login
        admin_login(client, env)
        
        # 2. Get existing challenges
        r = client.get(f"{CTFD_URL}/api/v1/challenges?view=admin", headers={"Accept": "application/json"})
        r.raise_for_status()
        existing_chals = {c["name"]: c for c in r.json().get("data", [])}
        
        # 3. Process each level from YAML
        for level in levels:
            chal_name = level["name"]
            chal_desc = level.get("description", "")
            flags = level.get("flags", [])

            # Try to find by ctfd_challenge_id first (most reliable), then by name
            chal_id = None
            chal_id_from_yaml = level.get("ctfd_challenge_id")
            existing_by_id = None
            if chal_id_from_yaml:
                existing_by_id = next((c for c in existing_chals.values() if c["id"] == chal_id_from_yaml), None)

            if existing_by_id:
                chal_id = existing_by_id["id"]
                logger.info(f"Challenge found by CTFd ID {chal_id}: '{existing_by_id['name']}' — updating.")
                client.patch(f"{CTFD_URL}/api/v1/challenges/{chal_id}", json={"state": "hidden"})
                # Update name and description in CTFd to match yaml
                update_payload = {
                    "name": chal_name,
                    "description": chal_desc,
                    "category": "Jailbreak",
                }
                r = client.patch(f"{CTFD_URL}/api/v1/challenges/{chal_id}", json=update_payload)
                if not r.is_success:
                    logger.warning(f"  → Could not update challenge details: {r.text}")
                else:
                    logger.info(f"  → Updated name/description for '{chal_name}'.")
            elif chal_name in existing_chals:
                logger.info(f"Challenge exists by name: '{chal_name}' — updating.")
                chal_id = existing_chals[chal_name]["id"]
                client.patch(f"{CTFD_URL}/api/v1/challenges/{chal_id}", json={"state": "hidden"})
                # Update description in CTFd to match yaml
                update_payload = {
                    "name": chal_name,
                    "description": chal_desc,
                    "category": "Jailbreak",
                }
                r = client.patch(f"{CTFD_URL}/api/v1/challenges/{chal_id}", json=update_payload)
                if not r.is_success:
                    logger.warning(f"  → Could not update challenge details: {r.text}")
                else:
                    logger.info(f"  → Updated description for '{chal_name}'.")
            else:
                logger.info(f"Creating new challenge: '{chal_name}'")
                create_payload = {
                    "name": chal_name,
                    "category": "Jailbreak",
                    "description": chal_desc,
                    "value": 100,  # default value
                    "state": "hidden",
                    "type": "standard",
                }
                r = client.post(f"{CTFD_URL}/api/v1/challenges", json=create_payload)
                r.raise_for_status()
                chal_id = r.json().get("data", {}).get("id")
                if not chal_id:
                    logger.error(f"Failed to create challenge '{chal_name}': {r.text}")
                    continue
                    
            # 4. Sync Flags for this challenge
            # First, get existing flags
            r = client.get(f"{CTFD_URL}/api/v1/flags")
            r.raise_for_status()
            existing_flags = [f for f in r.json().get("data", []) if f["challenge_id"] == chal_id]
            existing_flag_contents = {f["content"]: f for f in existing_flags}
            
            added_flags = 0
            for flag_content in flags:
                if flag_content not in existing_flag_contents:
                    # Add new flag
                    flag_payload = {
                        "challenge_id": chal_id,
                        "type": "static",
                        "content": flag_content,
                        "data": "case_insensitive"
                    }
                    client.post(f"{CTFD_URL}/api/v1/flags", json=flag_payload)
                    added_flags += 1
            
            if added_flags > 0:
                logger.info(f"  → Added {added_flags} new flags to '{chal_name}'.")
                
            # Make the challenge visible
            client.patch(f"{CTFD_URL}/api/v1/challenges/{chal_id}", json={"state": "visible"})
            logger.info(f"  → Challenge '{chal_name}' is synced and visible (CTFd ID: {chal_id}).\n")

    logger.info("🎉 CTFd sync complete!")


if __name__ == "__main__":
    sync_challenges()
