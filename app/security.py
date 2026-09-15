"""Password hashing, auth tokens and code generation — stdlib only."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from .config import SECRET_KEY, TOKEN_TTL
from .database import get_db
from .models import Psychologist

_SECRET = SECRET_KEY.encode("utf-8")
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no ambiguous 0/O/1/I/L


# ------------------------------------------------------------------ passwords
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return "pbkdf2$" + salt.hex() + "$" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, dk_hex = stored.split("$")
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


# --------------------------------------------------------------------- tokens
def create_token(psychologist_id: int, token_version: int = 1) -> str:
    payload = json.dumps({
        "sub": psychologist_id,
        "ver": token_version,
        "exp": int(time.time()) + TOKEN_TTL,
    })
    body = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    sig = hmac.new(_SECRET, body.encode("ascii"), hashlib.sha256).hexdigest()
    return body + "." + sig


def verify_token(token: str):
    """Возвращает (psychologist_id, token_version) либо None.

    Токены, выпущенные до появления версии, приходят без поля "ver" — им
    подставляется 0, то есть они не сойдутся ни с одной актуальной версией
    (минимум 1) и потребуют повторного входа. Это разовое неудобство при
    обновлении и правильное поведение по умолчанию.
    """
    try:
        body, sig = token.split(".")
        expected = hmac.new(_SECRET, body.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        pad = "=" * (-len(body) % 4)
        data = json.loads(base64.urlsafe_b64decode(body + pad))
        if int(data["exp"]) < time.time():
            return None
        return int(data["sub"]), int(data.get("ver", 0))
    except Exception:
        return None


# ----------------------------------------------------------------------- codes
def generate_code(length: int = 6) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


# ------------------------------------------------------------------ dependency
def get_current_psychologist(
    authorization: str = Header(None), db: Session = Depends(get_db)
) -> Psychologist:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Не авторизовано")
    claims = verify_token(authorization[7:])
    if not claims:
        raise HTTPException(status_code=401, detail="Сессия недействительна")
    pid, ver = claims
    user = db.get(Psychologist, pid)
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    if ver != (user.token_version or 1):
        raise HTTPException(status_code=401, detail="Сессия завершена. Войдите заново.")
    return user


def get_psychologist_for_download(
    authorization: str = Header(None),
    token: str = Query(None),
    db: Session = Depends(get_db),
) -> Psychologist:
    """Авторизация для скачивания файлов.

    Файл забирается обычной ссылкой, а не fetch, поэтому положить токен в
    заголовок нельзя — он передаётся параметром запроса. Токен в URL может
    осесть в истории браузера и логах, поэтому такой способ разрешён ТОЛЬКО
    здесь, на GET-эндпоинтах экспорта, а не в основной зависимости.
    """
    if authorization and authorization.startswith("Bearer "):
        raw = authorization[7:]
    elif token:
        raw = token
    else:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    claims = verify_token(raw)
    if not claims:
        raise HTTPException(status_code=401, detail="Сессия недействительна")
    pid, ver = claims
    user = db.get(Psychologist, pid)
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    if ver != (user.token_version or 1):
        raise HTTPException(status_code=401, detail="Сессия завершена. Войдите заново.")
    return user
