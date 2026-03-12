from fastapi import APIRouter
from pydantic import BaseModel
from app.services.admin_state import get_state, set_state

router = APIRouter(prefix="/admin", tags=["admin"])

class StateUpdate(BaseModel):
    value: str

@router.get("/state/{key}")
def read_state(key: str):
    val = get_state(key)
    return {"key": key, "value": val}

@router.post("/state/{key}")
def write_state(key: str, body: StateUpdate):
    set_state(key, body.value)
    return {"key": key, "value": body.value}
