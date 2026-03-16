import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from app.services.admin_state import get_state, set_state
from app.config import get_settings


def verify_admin_token(x_admin_token: str = Header(default=None)):
    secret = get_settings().ADMIN_SECRET_KEY
    if not x_admin_token or not hmac.compare_digest(x_admin_token, secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin token",
        )

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(verify_admin_token)]
)

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
