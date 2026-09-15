"""Настройка тестового окружения.

Делает корень проекта импортируемым (чтобы работал `import app.*`) и — что
важнее — подменяет базу на временный SQLite ДО первого импорта app.config.
Иначе config успевает вызвать load_dotenv() и подхватить боевую строку
подключения к Supabase: тесты пошли бы в рабочую базу школы.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_fd, _path = tempfile.mkstemp(suffix=".sqlite3")
os.close(_fd)
os.environ["DATABASE_URL"] = "sqlite:///" + _path.replace("\\", "/")
os.environ["SECRET_KEY"] = "test-only-secret-not-used-in-deploy"
# Регистрация в тестах идёт без кода приглашения.
os.environ["REGISTRATION_INVITE_CODE"] = ""
