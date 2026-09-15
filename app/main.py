"""Изолят — FastAPI application entry point."""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401  (register models on Base)
from .config import ALLOWED_ORIGINS
from .database import Base, engine
from .routers import alerts, audit, auth, dashboard, prevention, public, school

# Схема управляется миграциями Alembic (`alembic upgrade head`). create_all
# оставлен только для пустой базы — на уже существующей он не меняет ничего и
# молча оставляет схему устаревшей, из-за чего приложение падало бы на новых
# колонках. См. README, раздел «Миграции».
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Изолят", description="Раннее выявление социальной изоляции школьников")

# CORS. Фронтенд отдаётся этим же приложением, то есть с того же origin, —
# для обычной работы CORS не нужен вовсе, и по умолчанию middleware не
# подключается. Раньше здесь стоял allow_origins=["*"], из-за чего публичные
# эндпоинты опроса мог дёргать любой сторонний сайт. Если нужен доступ с
# другого хоста (демо с телефона по LAN), перечисли конкретные origin в
# переменной окружения ALLOWED_ORIGINS через запятую.
if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(alerts.router)
app.include_router(audit.router)
app.include_router(prevention.router)
app.include_router(school.router)
app.include_router(public.router)


@app.get("/api/health")
def health():
    """Проба для мониторинга и health check на Render."""
    return {"status": "ok"}

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

# Serve the static front-end. Mounted last so API routes take precedence.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
