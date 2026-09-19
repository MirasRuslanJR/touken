"""Изолят — FastAPI application entry point."""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401  (register models on Base)
from .config import ALLOWED_ORIGINS
from .routers import alerts, audit, auth, dashboard, prevention, public, school

# Схему создаёт и обновляет ТОЛЬКО Alembic (`alembic upgrade head`; на Render —
# в buildCommand, см. render.yaml). Здесь когда-то стоял create_all «на случай
# пустой базы», и именно он ломал развёртывание: на пустой базе он создавал
# таблицы, не записав версию в alembic_version, после чего upgrade падал на
# уже существующих таблицах. База оставалась с таблицами от новых моделей и
# без новых КОЛОНОК в старых таблицах (create_all их не добавляет никогда) —
# приложение падало с UndefinedColumn на первом же запросе.
# Тесты создают схему сами (tests/helpers.fresh_client).
# Как чинить такую базу — см. README, раздел «Миграции».

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
