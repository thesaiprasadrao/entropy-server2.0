from sqlalchemy.orm import Session

from app.models.admin_state import AdminState
from app.database import SessionLocal

def get_state(key: str) -> str | None:
    """Helper to get a global admin state directly."""
    with SessionLocal() as db:
        record = db.query(AdminState).filter(AdminState.key == key).first()
        return record.value if record else None

def set_state(key: str, value: str) -> None:
    """Helper to set a global admin state directly."""
    with SessionLocal() as db:
        record = db.query(AdminState).filter(AdminState.key == key).first()
        if record:
            record.value = value
        else:
            record = AdminState(key=key, value=value)
            db.add(record)
        db.commit()
