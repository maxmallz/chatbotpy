"""Read schema/table metadata from information_schema and summarize it.

Only information_schema is queried, so this is safe on the read-only MES connection.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import Engine, bindparam, text

SYSTEM_SCHEMAS = {"mysql", "information_schema", "performance_schema", "sys"}
TIME_TYPES = {"datetime", "timestamp", "date"}
NOTABLE_TYPES = {"vector", "json", "blob", "longblob", "longtext", "geometry"}

# Tables the plan expects, used to check a datasource against it.
EXPECTED_TABLES = {
    "mes": {"equipment", "sensor_tags", "sensor_readings", "alarms"},
    "chatbotpy": {"sessions", "events", "app_states", "user_states", "host_apps",
                  "analysis_embeddings"},
}


@dataclass
class Column:
    name: str
    data_type: str
    nullable: bool


@dataclass
class Table:
    schema: str
    name: str
    type: str  # BASE TABLE | VIEW
    rows: int  # estimate from information_schema
    size_bytes: int
    columns: list[Column] = field(default_factory=list)
    primary_key: list[str] = field(default_factory=list)
    indexes: dict[str, list[str]] = field(default_factory=dict)
    foreign_keys: list[tuple[str, str]] = field(default_factory=list)  # (column, schema.table.col)

    @property
    def fqn(self) -> str:
        return f"{self.schema}.{self.name}"


def list_schemas(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA")).scalars()
        return sorted(s for s in rows if s.lower() not in SYSTEM_SCHEMAS)


def fetch_tables(engine: Engine, schemas: list[str]) -> list[Table]:
    if not schemas:
        return []
    p = {"schemas": schemas}

    def q(sql: str):
        return text(sql).bindparams(bindparam("schemas", expanding=True))

    with engine.connect() as conn:
        # MySQL 8+ caches TABLE_ROWS for up to a day; read current estimates instead.
        conn.execute(text("SET SESSION information_schema_stats_expiry = 0"))
        tables = {
            (r.sch, r.tbl): Table(r.sch, r.tbl, r.ty, int(r.n or 0), int(r.sz or 0))
            for r in conn.execute(q(
                "SELECT TABLE_SCHEMA sch, TABLE_NAME tbl, TABLE_TYPE ty, TABLE_ROWS n, "
                "COALESCE(DATA_LENGTH,0)+COALESCE(INDEX_LENGTH,0) sz "
                "FROM information_schema.TABLES WHERE TABLE_SCHEMA IN :schemas"), p)
        }
        for r in conn.execute(q(
                "SELECT TABLE_SCHEMA sch, TABLE_NAME tbl, COLUMN_NAME c, DATA_TYPE dt, IS_NULLABLE n "
                "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA IN :schemas "
                "ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION"), p):
            if (t := tables.get((r.sch, r.tbl))) is not None:
                t.columns.append(Column(r.c, r.dt.lower(), r.n == "YES"))
        for r in conn.execute(q(
                "SELECT TABLE_SCHEMA sch, TABLE_NAME tbl, INDEX_NAME i, COLUMN_NAME c "
                "FROM information_schema.STATISTICS WHERE TABLE_SCHEMA IN :schemas "
                "ORDER BY TABLE_SCHEMA, TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX"), p):
            if (t := tables.get((r.sch, r.tbl))) is not None:
                if r.i == "PRIMARY":
                    t.primary_key.append(r.c)
                else:
                    t.indexes.setdefault(r.i, []).append(r.c)
        for r in conn.execute(q(
                "SELECT TABLE_SCHEMA sch, TABLE_NAME tbl, COLUMN_NAME c, REFERENCED_TABLE_SCHEMA rs, "
                "REFERENCED_TABLE_NAME rt, REFERENCED_COLUMN_NAME rc "
                "FROM information_schema.KEY_COLUMN_USAGE "
                "WHERE TABLE_SCHEMA IN :schemas AND REFERENCED_TABLE_NAME IS NOT NULL"), p):
            if (t := tables.get((r.sch, r.tbl))) is not None:
                t.foreign_keys.append((r.c, f"{r.rs}.{r.rt}.{r.rc}"))
    return sorted(tables.values(), key=lambda t: (t.schema, t.name))


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def analyze(tables: list[Table], schemas: list[str]) -> list[str]:
    """Return short findings, one line each."""
    findings: list[str] = []
    by_schema: dict[str, list[Table]] = defaultdict(list)
    for t in tables:
        by_schema[t.schema].append(t)

    for schema in schemas:
        ts = by_schema.get(schema, [])
        base = [t for t in ts if t.type == "BASE TABLE"]
        views = [t for t in ts if t.type != "BASE TABLE"]
        if not ts:
            findings.append(f"`{schema}`: no tables visible (empty, or the user lacks grants).")
            continue
        total_rows = sum(t.rows for t in base)
        findings.append(
            f"`{schema}`: {len(base)} tables, {len(views)} views, ~{total_rows:,} rows, "
            f"{_human(sum(t.size_bytes for t in base))}."
        )
        names = {t.name for t in ts}
        if expected := EXPECTED_TABLES.get(schema):
            missing = sorted(expected - names)
            findings.append(
                f"`{schema}` vs plan: missing {', '.join(missing)}." if missing
                else f"`{schema}` vs plan: all {len(expected)} expected tables present."
            )

    base = [t for t in tables if t.type == "BASE TABLE"]
    if big := sorted((t for t in base if t.rows), key=lambda t: t.rows, reverse=True)[:3]:
        findings.append("Largest: " + ", ".join(f"{t.fqn} (~{t.rows:,})" for t in big) + ".")
    if empty := [t.fqn for t in base if t.rows == 0]:
        findings.append(f"Empty (estimate 0 rows): {', '.join(empty)}.")
    if no_pk := [t.fqn for t in base if not t.primary_key]:
        findings.append(f"No primary key: {', '.join(no_pk)}.")

    fk_count = sum(len(t.foreign_keys) for t in base)
    shared = defaultdict(list)
    for t in base:
        for c in t.columns:
            if c.name.endswith("_id"):
                shared[c.name].append(t.name)
    joins = {c: ts for c, ts in shared.items() if len(ts) > 1}
    if fk_count:
        findings.append(f"{fk_count} declared foreign keys.")
    if joins:
        findings.append(
            ("No declared FKs; implicit join keys: " if not fk_count else "Shared join keys: ")
            + "; ".join(f"{c} ({', '.join(sorted(ts))})" for c, ts in sorted(joins.items()))
            + "."
        )

    series = []
    for t in base:
        time_cols = {c.name for c in t.columns if c.data_type in TIME_TYPES}
        indexed = {cols[i] for cols in [t.primary_key, *t.indexes.values()] for i in range(len(cols))}
        if time_cols and t.rows >= 10_000:
            note = "indexed" if time_cols & indexed else "time column NOT indexed"
            series.append(f"{t.fqn} ({note})")
    if series:
        findings.append(f"Time-series candidates: {', '.join(series)}.")

    notable = [
        f"{t.fqn}.{c.name}:{c.data_type}"
        for t in base for c in t.columns if c.data_type in NOTABLE_TYPES
    ]
    if notable:
        findings.append(f"Notable column types: {', '.join(notable)}.")
    return findings
