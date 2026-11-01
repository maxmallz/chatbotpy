"""Database engines.

- `app`: chatbotpy schema on MySQL 9 (read/write)
- `mes`: MES data (read-only)
- `chatbotjs`: the existing Node chatbot's DB on MySQL 8.4 (read-only, never written)
"""

from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.config import get_settings

ASYNC_DRIVERS = ("+aiomysql", "+asyncmy")


@dataclass(frozen=True)
class Datasource:
    name: str
    url: str
    read_only: bool


def datasources() -> dict[str, Datasource]:
    s = get_settings()
    return {
        "app": Datasource("app", s.app_db_url, read_only=False),
        "mes": Datasource("mes", s.mes_db_url, read_only=True),
        "chatbotjs": Datasource("chatbotjs", s.chatbotjs_db_url, read_only=True),
    }


def sync_url(url: str) -> str:
    """The CLI and MES repos are sync, so swap async MySQL drivers for pymysql."""
    for driver in ASYNC_DRIVERS:
        url = url.replace(driver, "+pymysql")
    return url


def safe_url(url: str) -> str:
    try:
        return make_url(url).render_as_string(hide_password=True)
    except ArgumentError:
        return "<unparseable url>"


def make_engine(url: str, read_only: bool = False) -> Engine:
    url = sync_url(url)
    connect_args = {"connect_timeout": 5} if url.startswith("mysql") else {}
    engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
    if read_only:

        @event.listens_for(engine, "connect")
        def _set_read_only(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("SET SESSION TRANSACTION READ ONLY")
            cur.close()

    return engine


@lru_cache
def get_engine(name: str) -> Engine:
    ds = datasources().get(name)
    if ds is None:
        raise KeyError(f"unknown datasource {name!r}; known: {', '.join(datasources())}")
    if not ds.url:
        raise ValueError(f"{name.upper()}_DB_URL is not set (see .env.example)")
    return make_engine(ds.url, read_only=ds.read_only)
