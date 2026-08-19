import os
import time
import uuid
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
# must run before any app.core import -- those read env vars at import time
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from apscheduler.schedulers.background import BackgroundScheduler
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.db_setup import run_migrations
from app.core.rate_limit import limiter
from app.core.reminders import send_pending_reminders
from app.core.notification_cleanup import cleanup_old_notifications
from app.routers import auth, requests as requests_router, admin, notifications

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("expense_tracker")

run_migrations()


def _run_reminder_check():
    db = SessionLocal()
    try:
        count = send_pending_reminders(db)
        if count:
            logger.info("Sent reminders for %d pending request(s)", count)
    except Exception:
        logger.exception("Reminder check failed")
    finally:
        db.close()


def _run_notification_cleanup():
    db = SessionLocal()
    try:
        deleted = cleanup_old_notifications(db)
        if deleted:
            logger.info("Cleaned up %d old, read notification(s)", deleted)
    except Exception:
        logger.exception("Notification cleanup failed")
    finally:
        db.close()


scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Every hour by default; each run only reminds requests that have crossed
    # REMINDER_THRESHOLD_DAYS and haven't been reminded about recently, so a
    # frequent check interval doesn't translate into frequent notifications.
    interval_minutes = int(os.getenv("REMINDER_CHECK_INTERVAL_MINUTES", "60"))
    scheduler.add_job(_run_reminder_check, "interval", minutes=interval_minutes, id="reminder_check")
    # Once a day is plenty for cleanup -- it's not urgent, just housekeeping.
    scheduler.add_job(_run_notification_cleanup, "interval", hours=24, id="notification_cleanup")
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="CDF Expense & Reimbursement Tracker API", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = str(duration_ms)
    logger.info(
        "request_id=%s method=%s path=%s status=%d duration_ms=%s",
        request_id, request.method, request.url.path, response.status_code, duration_ms,
    )
    return response


# Never leak internal stack traces / DB errors to the client.
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again."},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # exc.errors() can contain raw exception objects (e.g. from a custom
    # validator) that json can't serialize directly, so stringify everything.
    safe_errors = [
        {
            "field": ".".join(str(p) for p in err.get("loc", [])),
            "message": str(err.get("msg", "Invalid value")),
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid request data", "errors": safe_errors},
    )


app.include_router(auth.router, prefix="/api")
app.include_router(requests_router.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")

# same handlers, also reachable pinned to an explicit version
app.include_router(auth.router, prefix="/api/v1")
app.include_router(requests_router.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")


@app.get("/api/health")
def health_check():
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_ok = True
    except Exception:
        logger.exception("Health check DB connectivity failed")
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "unreachable",
    }
