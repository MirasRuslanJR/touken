"""Аутентификация и регистрация сотрудников школы."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import assist
from ..config import REGISTRATION_INVITE_CODE
from ..database import get_db
from ..models import ROLE_ADMIN, ROLE_PSYCHOLOGIST, ROLES, Psychologist, School
from ..permissions import require_admin
from ..ratelimit import check as rate_limit, client_ip
from ..schemas import LoginIn, PasswordChangeIn, RegisterIn, SchoolIn, UserRoleIn
from ..security import (
    create_token,
    generate_code,
    get_current_psychologist,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _public(user: Psychologist, school: School = None):
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role or ROLE_PSYCHOLOGIST,
        "school_id": user.school_id,
        "school_name": school.name if school is not None else None,
    }


def _with_school(db, user):
    school = db.get(School, user.school_id) if user.school_id else None
    return _public(user, school)


@router.post("/register")
def register(data: RegisterIn, request: Request, db: Session = Depends(get_db)):
    """Регистрация сотрудника.

    Свободной она быть не может: аккаунт даёт доступ к персональным данным
    несовершеннолетних. Код приглашения выдаёт школа — по нему сотрудник
    попадает именно в неё. Первый зарегистрировавшийся в школе становится её
    администратором, остальные — психологами.
    """
    rate_limit("register:" + client_ip(request), limit=5, window=3600)

    code = (data.invite_code or "").strip()
    school = db.query(School).filter(School.invite_code == code).first() if code else None

    if school is None:
        # Код школы не подошёл. Разрешаем регистрацию без школы только если
        # глобальный REGISTRATION_INVITE_CODE не задан (локальное демо).
        if REGISTRATION_INVITE_CODE:
            if code != REGISTRATION_INVITE_CODE:
                raise HTTPException(status_code=403, detail="Неверный код приглашения школы")
        elif code:
            raise HTTPException(status_code=403, detail="Неверный код приглашения школы")

    email = data.email.strip().lower()
    if db.query(Psychologist).filter(Psychologist.email == email).first():
        raise HTTPException(status_code=409, detail="Пользователь с таким e-mail уже существует")

    role = ROLE_PSYCHOLOGIST
    if school is not None:
        first_in_school = not db.query(Psychologist).filter(Psychologist.school_id == school.id).first()
        if first_in_school:
            role = ROLE_ADMIN

    user = Psychologist(
        email=email,
        password_hash=hash_password(data.password),
        full_name=(data.full_name or email).strip(),
        school_id=school.id if school is not None else None,
        role=role,
        token_version=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"token": create_token(user.id, user.token_version), "user": _public(user, school), "features": {"ai_assist": assist.is_configured()}}


@router.post("/schools")
def create_school(data: SchoolIn, request: Request, db: Session = Depends(get_db)):
    """Регистрация новой школы. Возвращает код приглашения для сотрудников.

    Открыта, только если не задан REGISTRATION_INVITE_CODE: на управляемом
    стенде школы заводит оператор сервиса, а не любой посетитель.
    """
    if REGISTRATION_INVITE_CODE:
        raise HTTPException(
            status_code=403,
            detail="Регистрация школ на этом стенде закрыта. Обратитесь к администратору сервиса.",
        )
    rate_limit("school:" + client_ip(request), limit=3, window=3600)

    for _ in range(50):
        invite = generate_code(8)
        if not db.query(School).filter(School.invite_code == invite).first():
            break
    else:
        raise HTTPException(500, "Не удалось сгенерировать код приглашения")

    school = School(name=data.name.strip(), city=(data.city or "").strip() or None, invite_code=invite)
    db.add(school)
    db.commit()
    db.refresh(school)
    return {"school": {"id": school.id, "name": school.name, "city": school.city, "invite_code": school.invite_code}}


@router.post("/login")
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    # Защита от брутфорса: не больше 10 попыток входа с одного IP за 5 минут.
    rate_limit("login:" + client_ip(request), limit=10, window=300)
    email = data.email.strip().lower()
    user = db.query(Psychologist).filter(Psychologist.email == email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный e-mail или пароль")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Учётная запись отключена администратором школы")
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return {"token": create_token(user.id, user.token_version or 1), "user": _with_school(db, user), "features": {"ai_assist": assist.is_configured()}}


@router.post("/logout")
def logout(user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    """Настоящий серверный выход: инкремент версии обесценивает все выданные
    токены этого сотрудника, включая тот, что остался в браузере на школьном
    компьютере. Раньше токен жил до истечения TTL в 7 дней."""
    user.token_version = (user.token_version or 1) + 1
    db.commit()
    return {"ok": True}


@router.post("/password")
def change_password(
    data: PasswordChangeIn,
    user: Psychologist = Depends(get_current_psychologist),
    db: Session = Depends(get_db),
):
    """Смена пароля разлогинивает все остальные сессии — если пароль меняют
    из-за того, что его узнали, старый вход должен перестать работать."""
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Текущий пароль неверен")
    user.password_hash = hash_password(data.new_password)
    user.token_version = (user.token_version or 1) + 1
    db.commit()
    db.refresh(user)
    return {"token": create_token(user.id, user.token_version), "user": _with_school(db, user), "features": {"ai_assist": assist.is_configured()}}


@router.get("/me")
def me(user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    # features: что доступно на этом стенде. Интерфейс по нему решает, стоит
    # ли показывать кнопку, — предлагать действие, которое заведомо вернёт
    # ошибку, хуже, чем не предлагать вовсе.
    return {
        "user": _with_school(db, user),
        "features": {"ai_assist": assist.is_configured()},
    }


# ------------------------------------------------- управление сотрудниками
@router.get("/staff")
def list_staff(user: Psychologist = Depends(require_admin), db: Session = Depends(get_db)):
    rows = (
        db.query(Psychologist)
        .filter(Psychologist.school_id == user.school_id)
        .order_by(Psychologist.full_name)
        .all()
    )
    school = db.get(School, user.school_id)
    return {
        "invite_code": school.invite_code if school else None,
        "staff": [{
            "id": u.id, "email": u.email, "full_name": u.full_name,
            "role": u.role, "is_active": bool(u.is_active),
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        } for u in rows],
    }


@router.post("/staff/{uid}/reset-password")
def reset_staff_password(
    uid: int,
    user: Psychologist = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Сброс пароля сотрудника администратором школы.

    Восстановления по почте нет — отправлять письма школьному сервису неоткуда,
    а «секретный вопрос» защитой не является. Поэтому пароль сбрасывает живой
    человек, который может подтвердить личность коллеги очно: администратор
    выдаёт временный пароль, а сотрудник меняет его при первом входе.

    Все прежние сессии сотрудника при этом завершаются: если пароль сбрасывают
    потому, что доступ утёк, старый вход должен перестать работать сразу.
    """
    target = db.get(Psychologist, uid)
    if not target or target.school_id != user.school_id:
        raise HTTPException(404, "Сотрудник не найден")
    if target.id == user.id:
        raise HTTPException(400, "Свой пароль меняйте через «Аккаунт» — так он не попадёт на экран")

    temporary = generate_code(5) + "-" + generate_code(5)
    target.password_hash = hash_password(temporary)
    target.token_version = (target.token_version or 1) + 1
    db.commit()
    return {"temporary_password": temporary, "email": target.email}


@router.put("/staff/{uid}")
def update_staff(
    uid: int,
    data: UserRoleIn,
    user: Psychologist = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.get(Psychologist, uid)
    if not target or target.school_id != user.school_id:
        raise HTTPException(404, "Сотрудник не найден")
    if target.id == user.id:
        raise HTTPException(400, "Нельзя изменить собственную роль или доступ")

    if data.role is not None:
        if data.role not in ROLES:
            raise HTTPException(400, "Неизвестная роль")
        target.role = data.role
    if data.is_active is not None:
        target.is_active = bool(data.is_active)
        if not target.is_active:
            # Отключение доступа должно действовать сразу, а не через 7 дней.
            target.token_version = (target.token_version or 1) + 1
    db.commit()
    return {"staff": {"id": target.id, "email": target.email, "role": target.role,
                      "is_active": bool(target.is_active)}}
