"""
Loads levels from levels.yaml and upserts them into the database on startup.

Called from app/main.py on_startup so the DB always reflects the config file.
No manual SQL migrations needed when adding/editing levels.
"""
import random
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from app.models.level import Level
from app.database import SessionLocal

LEVELS_FILE = Path(__file__).parent.parent.parent / "levels.yaml"


def load_levels_config() -> list[dict]:
    if not LEVELS_FILE.exists():
        raise FileNotFoundError(f"levels.yaml not found at {LEVELS_FILE}")
    with open(LEVELS_FILE, "r") as f:
        data = yaml.safe_load(f)
    return data.get("levels", [])


def seed_levels_from_config(db: Session) -> None:
    """
    Upsert levels from levels.yaml into the DB.
    Stores flag pool as a comma-separated string in system_prompt is NOT used here;
    flags are stored on the Level model's `flag_pool` field (added as a Text column).
    """
    config_levels = load_levels_config()

    for cfg in config_levels:
        level_id = cfg["id"]
        flags = cfg.get("flags", [])
        flag_pool_str = ",".join(flags)

        existing = db.query(Level).filter(Level.id == level_id).first()
        if existing:
            existing.name = cfg["name"]
            existing.description = cfg.get("description", "")
            existing.system_prompt = cfg.get("system_prompt", "")
            existing.flag_pool = flag_pool_str
        else:
            db.add(Level(
                id=level_id,
                level_number=level_id,
                name=cfg["name"],
                description=cfg.get("description", ""),
                system_prompt=cfg.get("system_prompt", ""),
                flag_pool=flag_pool_str,
            ))

    db.commit()


def pick_flag_from_pool(level: Level) -> str:
    """Pick a random flag from the level's flag pool."""
    if not level.flag_pool:
        raise ValueError(f"Level {level.id} has no flags configured in levels.yaml")
    flags = [f.strip() for f in level.flag_pool.split(",") if f.strip()]
    return random.choice(flags)
