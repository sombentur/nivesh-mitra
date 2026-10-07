"""NiveshMitra backend entry point.

Run:  uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
It listens on 127.0.0.1 only, so other devices on your Wi-Fi can't reach it.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import scheduler
from app.api import dashboard as dashboard_api
from app.api import market as market_api
from app.api import market_calendar as calendar_api
from app.api import news as news_api
from app.api import data as data_api
from app.api import goals as goals_api
from app.api import mf as mf_api
from app.api import plan as plan_api
from app.api import profile as profile_api
from app.api import settings as settings_api
from app.api import setup as setup_api
from app.api import trading as trading_api
from app.auth import router as auth_router
from app.db.migrate import upgrade_to_head

VERSION = "0.1.0"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_HEADER = "x-nm-csrf"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    upgrade_to_head()
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="NiveshMitra", version=VERSION, lifespan=lifespan)


@app.middleware("http")
async def csrf_guard(request: Request, call_next):
    """Cookie-authenticated writes must carry a custom header, which other websites cannot add."""
    if request.method in UNSAFE_METHODS and request.url.path.startswith("/api/"):
        if request.headers.get(CSRF_HEADER) != "1":
            return JSONResponse({"detail": "Missing CSRF header"}, status_code=403)
    return await call_next(request)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": VERSION, "decision_only": True}


app.include_router(setup_api.router)
app.include_router(auth_router.router)
app.include_router(settings_api.router)
app.include_router(profile_api.router)
app.include_router(goals_api.router)
app.include_router(mf_api.router)
app.include_router(plan_api.router)
app.include_router(data_api.router)
app.include_router(dashboard_api.router)
app.include_router(market_api.router)
app.include_router(calendar_api.router)
app.include_router(news_api.router)
app.include_router(trading_api.router)
