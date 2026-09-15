"""SQLAlchemy engine / session setup.

Рабочая база — PostgreSQL (Supabase). SQLite поддерживается для тестов и для
локального запуска без своего сервера БД.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DATABASE_URL

if "YOUR-PROJECT-REF" in DATABASE_URL:
    raise RuntimeError(
        "Не задана строка подключения к базе.\n"
        "Скопируй .env.example в .env и впиши DATABASE_URL:\n"
        "  Supabase -> Project Settings -> Database -> Connection string -> URI,\n"
        "  замени схему на postgresql+psycopg2:// и подставь пароль."
    )

IS_SQLITE = DATABASE_URL.startswith("sqlite")

# pool_pre_ping спасает от «сдохших» соединений в пуле Supabase.
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=1800)


if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        """SQLite по умолчанию ИГНОРИРУЕТ внешние ключи.

        Без этого ON DELETE CASCADE не срабатывает: при удалении класса его
        ученики и срезы остаются сиротами, а поскольку SQLite переиспользует
        освободившиеся id, следующий созданный класс «наследует» чужих
        учеников. Один раз это уже сломало демо-данные — класс из 14 человек
        показывал 28. На PostgreSQL проблемы нет, но тесты идут на SQLite и
        должны проверять то же поведение, что и в бою.
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
