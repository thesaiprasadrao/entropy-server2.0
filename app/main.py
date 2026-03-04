import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health, levels, chat, leaderboard
from app.database import check_db_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Entropy — AI Jailbreak Sprint Backend",
    version="1.0.0",
    description="Secure backend for AI prompt jailbreak challenges.",
)

# ── CORS (allow Nginx frontend on port 80) ─────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://localhost:80", "http://127.0.0.1"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(levels.router)
app.include_router(chat.router)
app.include_router(leaderboard.router)


# ── Startup ────────────────────────────────────────────────────────────────────
@app.on_event("startup")
def on_startup():
    logger.info("Starting Entropy backend…")
    if check_db_connection():
        logger.info("Database connection: OK")
    else:
        logger.warning("Database connection: FAILED — check DB container")
