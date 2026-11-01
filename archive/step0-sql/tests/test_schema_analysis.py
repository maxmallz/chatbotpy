from app.datasource.ping import _major
from app.datasource.schema import Column, Table, analyze
from app.db import safe_url, sync_url


def _t(name, rows, cols, pk=(), indexes=None, schema="mes"):
    return Table(schema, name, "BASE TABLE", rows, rows * 100,
                 columns=[Column(c, dt, False) for c, dt in cols],
                 primary_key=list(pk), indexes=indexes or {})


def test_analyze_flags_plan_gaps_joins_and_series():
    tables = [
        _t("equipment", 40, [("equipment_id", "varchar"), ("name", "varchar")], pk=["equipment_id"]),
        _t("sensor_readings", 2_000_000,
           [("equipment_id", "varchar"), ("tag", "varchar"), ("ts", "datetime"),
            ("value", "double")],
           indexes={"idx": ["equipment_id", "tag", "ts"]}),
        _t("alarms", 50_000, [("alarm_id", "bigint"), ("equipment_id", "varchar"),
                              ("start_ts", "datetime")], pk=["alarm_id"]),
    ]
    out = "\n".join(analyze(tables, ["mes"]))

    assert "missing sensor_tags" in out
    assert "No primary key: mes.sensor_readings" in out
    assert "implicit join keys: equipment_id (alarms, equipment, sensor_readings)" in out
    assert "mes.sensor_readings (indexed)" in out
    assert "mes.alarms (time column NOT indexed)" in out


def test_analyze_reports_invisible_schema():
    assert "no tables visible" in analyze([], ["mes"])[0]


def test_urls():
    assert sync_url("mysql+aiomysql://u:p@h/db") == "mysql+pymysql://u:p@h/db"
    assert "p@" not in safe_url("mysql+pymysql://u:p@h/db")


def test_vector_support_by_version():
    assert _major("9.1.0") >= 9
    assert _major("8.4.3") < 9
    assert _major(None) == 0
