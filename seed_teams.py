"""
seed_teams.py — Pre-seed registered teams into the users table.

Usage:
    docker compose exec backend python3 seed_teams.py teams.csv

CSV format (no header required, or with header row detected automatically):
    TeamName
    Team Alpha
    Spirit Squad
    ...

Or with auto-assigned IDs (optional second column, ignored — IDs are auto-generated):
    TeamName,Email
    Team Alpha,alpha@example.com

Run this once before the event. Re-running is safe — existing teams are skipped.
"""
import csv
import hashlib
import sys
from pathlib import Path

# ── Bootstrap Django-free SQLAlchemy session ───────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from app.database import SessionLocal
from app.models.user import User


def stable_id(username: str) -> int:
    h = hashlib.sha256(username.lower().strip().encode()).hexdigest()
    return int(h[:8], 16)


def seed_from_csv(filepath: str) -> None:
    db = SessionLocal()
    try:
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Auto-skip header if first column looks like a label
        if rows and rows[0][0].lower().strip() in ("teamname", "team name", "team", "name"):
            rows = rows[1:]

        added = 0
        skipped = 0
        for row in rows:
            if not row:
                continue
            team_name = row[0].strip()
            if not team_name:
                continue

            existing = db.query(User).filter(User.username == team_name).first()
            if existing:
                print(f"  skip  {team_name!r} (already exists, id={existing.ctf_user_id})")
                skipped += 1
                continue

            uid = stable_id(team_name)
            db.add(User(ctfd_user_id=uid, username=team_name))
            print(f"  add   {team_name!r} → id={uid}")
            added += 1

        db.commit()
        print(f"\nDone. {added} added, {skipped} skipped.")

    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 seed_teams.py <teams.csv>")
        sys.exit(1)
    seed_from_csv(sys.argv[1])
