import os
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

from app.core.database import Base, engine, SessionLocal
from app.core.reminders import send_pending_reminders
from app.routers import auth, requests as requests_router, admin, notifications

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("expense_tracker")

Base.metadata.create_all(bind=engine)


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


scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Every hour by default; each run only reminds requests that have crossed
    # REMINDER_THRESHOLD_DAYS and haven't been reminded about recently, so a
    # frequent check interval doesn't translate into frequent notifications.
    interval_minutes = int(os.getenv("REMINDER_CHECK_INTERVAL_MINUTES", "60"))
    scheduler.add_job(_run_reminder_check, "interval", minutes=interval_minutes, id="reminder_check")
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="CDF Expense & Reimbursement Tracker API", lifespan=lifespan)

allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


app.include_router(auth.router)
app.include_router(requests_router.router)
app.include_router(admin.router)
app.include_router(notifications.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
