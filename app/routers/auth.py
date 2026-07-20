"""Psychologist authentication."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Psychologist
from ..schemas import LoginIn, RegisterIn
from ..security import (
    create_token,
    get_current_psychologist,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _public(user: Psychologist):
    return {"id": user.id, "email": user.email, "full_name": user.full_name}


@router.post("/register")
def register(data: RegisterIn, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    if db.query(Psychologist).filter(Psychologist.email == email).first():
        raise HTTPException(status_code=409, detail="Пользователь с таким e-mail уже существует")
    user = Psychologist(
        email=email,
        password_hash=hash_password(data.password),
        full_name=(data.full_name or email).strip(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"token": create_token(user.id), "user": _public(user)}


@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    user = db.query(Psychologist).filter(Psychologist.email == email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный e-mail или пароль")
    return {"token": create_token(user.id), "user": _public(user)}


@router.get("/me")
def me(user: Psychologist = Depends(get_current_psychologist)):
    return {"user": _public(user)}
