"""Runs against the compose MySQL 9 (scripts/docker-test.sh); skipped when it isn't reachable."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.datasource.ping import ping
from app.datasource.schema import analyze, fetch_tables
from app.db import get_engine


@pytest.fixture(scope="module")
def mes():
    if not ping("mes").ok:
        pytest.skip("mes datasource not reachable")
    return get_engine("mes")


def test_mes_ping_is_read_only_with_vector():
    r = ping("mes")
    if not r.ok:
        pytest.skip("mes datasource not reachable")
    assert r.read_only and r.supports_vector


def test_fetch_tables_reads_real_metadata(mes):
    tables = {t.name: t for t in fetch_tables(mes, ["mes"])}
    assert {"equipment", "sensor_tags", "sensor_readings", "alarms"} <= tables.keys()
    assert tables["sensor_readings"].primary_key == ["equipment_id", "tag", "ts"]
    assert tables["alarms"].indexes["idx_equipment_start"] == ["equipment_id", "start_ts"]
    assert "all 4 expected tables present" in "\n".join(analyze(list(tables.values()), ["mes"]))


def test_mes_engine_rejects_writes(mes):
    with pytest.raises(DBAPIError), mes.connect() as conn:
        conn.execute(text("CREATE TEMPORARY TABLE nope (id INT)"))
        conn.execute(text("DELETE FROM equipment"))
