"""ACUTE-GOAL: chatbotpy MUST NOT have any direct SQL. Data comes only from core-svc over HTTP."""

import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"
PYPROJECT = APP.parent / "pyproject.toml"

DB_MODULES = re.compile(
    r"^\s*(import|from)\s+(sqlalchemy|pymysql|aiomysql|asyncmy|mysql|MySQLdb|sqlite3|psycopg2?|"
    r"clickhouse_connect|clickhouse_driver|google\.adk\.sessions)\b",
    re.MULTILINE,
)
SQL_TEXT = re.compile(r"\b(SELECT\s+.+\s+FROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|"
                      r"CREATE\s+TABLE|DROP\s+TABLE)\b", re.IGNORECASE)
DB_PACKAGES = re.compile(r'"(sqlalchemy|pymysql|aiomysql|asyncmy|mysqlclient|clickhouse[-_]\w+)', re.IGNORECASE)


def sources():
    return sorted(APP.rglob("*.py"))


def test_app_has_sources():
    assert sources(), "no app/*.py found"


def test_no_database_drivers_imported():
    offenders = [str(p) for p in sources() if DB_MODULES.search(p.read_text())]
    assert not offenders, f"database modules imported in: {offenders}"


def test_no_sql_statements():
    offenders = [f"{p}: {m.group(0)}" for p in sources() for m in SQL_TEXT.finditer(p.read_text())]
    assert not offenders, f"SQL found: {offenders}"


def test_no_database_dependencies():
    assert not DB_PACKAGES.search(PYPROJECT.read_text()), "database driver listed in pyproject.toml"
