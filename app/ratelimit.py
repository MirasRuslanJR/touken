"""Очень простой in-memory rate limiter (в пределах одного процесса).

Хватает для MVP / демо на одном инстансе: счётчик сбрасывается при перезапуске
и не разделяется между воркерами. Цель — закрыть очевидный перебор:
брутфорс пароля на /login и перебор кодов учеников на /start.
"""
import threading
import time

from fastapi import HTTPException, Request

_lock = threading.Lock()
_hits: dict[str, list[float]] = {}


def client_ip(request: Request) -> str:
    """IP клиента с учётом прокси (Render/облако кладёт реальный IP в
    X-Forwarded-For). Берём первый адрес из цепочки."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check(key: str, limit: int, window: int) -> None:
    """Разрешает не более `limit` обращений с ключом `key` за `window` секунд.
    При превышении бросает 429. Скользящее окно."""
    now = time.time()
    with _lock:
        recent = [t for t in _hits.get(key, []) if now - t < window]
        if len(recent) >= limit:
            _hits[key] = recent
            retry = max(1, int(window - (now - recent[0])) + 1)
            raise HTTPException(
                status_code=429,
                detail=f"Слишком много попыток. Попробуйте через {retry} с.",
            )
        recent.append(now)
        _hits[key] = recent
