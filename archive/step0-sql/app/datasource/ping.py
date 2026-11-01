import time
from dataclasses import dataclass

from sqlalchemy import text

from app.db import datasources, get_engine, safe_url


@dataclass
class PingResult:
    target: str
    url: str
    ok: bool
    latency_ms: float | None = None
    server_version: str | None = None
    current_user: str | None = None
    database: str | None = None
    read_only: bool | None = None
    expected_read_only: bool | None = None
    supports_vector: bool | None = None  # VECTOR type needs MySQL 9+
    error: str | None = None


def _major(version: str) -> int:
    try:
        return int(version.split(".")[0])
    except (ValueError, AttributeError):
        return 0


def ping(target: str) -> PingResult:
    ds = datasources()[target]
    result = PingResult(target, safe_url(ds.url), ok=False, expected_read_only=ds.read_only)
    try:
        engine = get_engine(target)
        start = time.perf_counter()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            result.latency_ms = round((time.perf_counter() - start) * 1000, 1)
            row = conn.execute(
                text(
                    "SELECT VERSION(), CURRENT_USER(), DATABASE(), "
                    "@@session.transaction_read_only"
                )
            ).one()
        result.server_version, result.current_user, result.database = row[0], row[1], row[2]
        result.read_only = bool(row[3])
        result.supports_vector = _major(result.server_version) >= 9
        result.ok = True
    except Exception as exc:  # noqa: BLE001 -- report, don't raise: ping is a diagnostic
        result.error = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
    return result
