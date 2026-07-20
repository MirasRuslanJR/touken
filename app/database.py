"""SQLAlchemy engine / session setup — PostgreSQL (Supabase) only."""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DATABASE_URL

if "YOUR-PROJECT-REF" in DATABASE_URL:
    raise RuntimeError(
        "Не задана строка подключения к Supabase.\n"
        "Открой app/config.py и впиши свою DATABASE_URL:\n"
        "  Supabase -> Project Settings -> Database -> Connection string -> URI,\n"
        "  замени схему на postgresql+psycopg2:// и подставь пароль."
    )

# pool_pre_ping спасает от «сдохших» соединений в пуле Supabase.
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=1800)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
