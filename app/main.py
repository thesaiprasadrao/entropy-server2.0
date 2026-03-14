import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health, levels, chat, leaderboard, submit_flag, admin, hints
from app.database import check_db_connection, SessionLocal, Base, engine
import app.models  # noqa: F401 — ensures all models are registered with Base
from app.services.levels_loader import seed_levels_from_config
from app.scripts.sync_ctfd import sync_challenges
import threading
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Entropy — AI Jailbreak Sprint Backend",
    version="1.0.0",
    description="Secure backend for AI prompt jailbreak challenges.",
    docs_url=None,  # disable public Swagger UI
    redoc_url=None,  # disable public ReDoc
)

# ── CORS (allow Nginx frontend on port 80) ─────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://localhost:80", "http://127.0.0.1"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

from fastapi import Request, status
from fastapi.responses import JSONResponse
from app.services.admin_state import get_state


@app.middleware("http")
async def check_global_shutdown(request: Request, call_next):
    path = request.url.path
    is_admin = path == "/admin" or path.startswith("/admin/")
    if not is_admin and get_state("global_shutdown") == "true":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "System is down for maintenance"},
        )
    return await call_next(request)


# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(levels.router)
app.include_router(chat.router)
app.include_router(leaderboard.router)
app.include_router(submit_flag.router)
app.include_router(admin.router)
app.include_router(hints.router)


# ── Startup ────────────────────────────────────────────────────────────────────
@app.on_event("startup")
def on_startup():
    logger.info("Starting Entropy backend…")
    # Create all tables if they don't exist yet
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")

    if check_db_connection():
        logger.info("Database connection: OK")
    else:
        logger.warning("Database connection: FAILED — check DB container")

    # Seed/update levels from levels.yaml
    try:
        db = SessionLocal()
        seed_levels_from_config(db)
        db.close()
        logger.info("Levels seeded from levels.yaml")
    except Exception as e:
        logger.error(f"Failed to seed levels: {e}")

    # Auto-sync CTFd challenges in the background
    def delayed_sync():
        logger.info("Waiting for CTFd to initialize before syncing challenges...")
        time.sleep(5)  # Give CTFd a few seconds to start up if both are booting
        try:
            sync_challenges()
        except Exception as e:
            logger.error(f"Auto-sync failed (CTFd might not be set up yet): {e}")

    threading.Thread(target=delayed_sync, daemon=True).start()
