"""FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import FRONTEND_ORIGIN
from app.routes import actions, admin, alleges, audit as audit_routes, process
from app.services import audit as audit_service, cases as cases_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Initialise both SQLite DBs on startup (idempotent)
    audit_service.init_db()
    cases_service.init_db()
    yield


app = FastAPI(
    title="Allege Automation Backend",
    description="Prototype: automates allege triage for Nomura OTC Settlements.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://localhost:8080", "http://127.0.0.1:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(alleges.router, prefix="/api/alleges", tags=["alleges"])
app.include_router(process.router, prefix="/api/process", tags=["process"])
app.include_router(actions.router, prefix="/api/actions", tags=["actions"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(audit_routes.router, prefix="/api/audit", tags=["audit"])


@app.get("/api/health")
def health():
    return {"status": "ok", "version": app.version}
