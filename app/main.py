"""Изолят — FastAPI application entry point."""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401  (register models on Base)
from .database import Base, engine
from .routers import auth, dashboard, public

# Create tables on startup in the configured Supabase/PostgreSQL database.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Изолят", description="Раннее выявление социальной изоляции школьников")

# CORS: allow_origins=["*"] is a DELIBERATE choice for the local demo /
# hackathon, not a forgotten default. The front-end is served from the same
# origin as the API, so CORS isn't actually needed for normal use; the
# wildcard just makes it painless to open the survey page or the dashboard
# from another device/host on the LAN during the demo. Auth uses a Bearer
# token (not cookies) and allow_credentials is False, so a wildcard origin is
# safe here. For a real deployment, replace "*" with the concrete front-end
# origin(s).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(public.router)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

# Serve the static front-end. Mounted last so API routes take precedence.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
