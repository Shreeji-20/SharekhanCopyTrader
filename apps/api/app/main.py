from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import accounts, auth, copy_groups, copy_sessions, copy_settings, dashboard, live, logs, portfolio, script_master, system
from app.services.live_copy import live_copy_manager

settings = get_settings()

app = FastAPI(title="Copy Trading Main API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.on_event("startup")
async def start_live_copy_sessions() -> None:
    await live_copy_manager.resume_running_sessions()


@app.on_event("shutdown")
async def stop_live_copy_sessions() -> None:
    await live_copy_manager.shutdown()


app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(copy_groups.router)
app.include_router(copy_sessions.router)
app.include_router(copy_settings.router)
app.include_router(portfolio.router)
app.include_router(logs.router)
app.include_router(dashboard.router)
app.include_router(live.router)
app.include_router(script_master.router)
app.include_router(system.router)
