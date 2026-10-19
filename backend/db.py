import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL DEFAULT 'other',
    severity TEXT NOT NULL DEFAULT 'low',
    priority TEXT NOT NULL DEFAULT 'low',
    description TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    location_name TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    source TEXT NOT NULL DEFAULT 'manual',
    transcript TEXT,
    ai_summary TEXT,
    details TEXT,
    ai_processed INTEGER NOT NULL DEFAULT 0,
    ai_error TEXT,
    anonymous_id_sha256 TEXT,
    occurred_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);
CREATE INDEX IF NOT EXISTS idx_reports_type ON reports(type);

CREATE TABLE IF NOT EXISTS quarter_heads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    wa_number TEXT NOT NULL,
    quarter_name TEXT NOT NULL,
    city TEXT,
    latitude REAL,
    longitude REAL,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    verified_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_heads_status ON quarter_heads(status);
CREATE INDEX IF NOT EXISTS idx_heads_number ON quarter_heads(wa_number);
"""


@contextmanager
def connection():
    conn = sqlite3.connect(config.DATABASE_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connection() as conn:
        conn.executescript(SCHEMA)


def utc_now() -> str:
    value = datetime.now(timezone.utc).replace(microsecond=0)
    return value.isoformat().replace("+00:00", "Z")


def report_from_row(row: sqlite3.Row) -> dict:
    details = None
    if row["details"]:
        try:
            details = json.loads(row["details"])
        except (TypeError, ValueError):
            details = None
    return {
        "id": row["id"],
        "type": row["type"],
        "severity": row["severity"],
        "priority": row["priority"],
        "description": row["description"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "location_name": row["location_name"],
        "status": row["status"],
        "source": row["source"],
        "transcript": row["transcript"],
        "ai_summary": row["ai_summary"],
        "details": details,
        "ai_processed": bool(row["ai_processed"]),
        "ai_error": row["ai_error"],
        "occurred_at": row["occurred_at"],
        "created_at": row["created_at"],
    }


def head_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "wa_number_masked": mask_number(row["wa_number"]),
        "quarter_name": row["quarter_name"],
        "city": row["city"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "has_id_document": False,
        "notes": row["notes"],
        "status": row["status"],
        "created_at": row["created_at"],
        "verified_at": row["verified_at"],
    }


def mask_number(number: str) -> str:
    digits = "".join(ch for ch in (number or "") if ch.isdigit())
    if len(digits) <= 3:
        return "***"
    return "***" + digits[-3:]


def create_report(data: dict) -> dict:
    now = utc_now()
    details = data.get("details")
    if details is not None and not isinstance(details, str):
        details = json.dumps(details, ensure_ascii=False)
    with connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO reports (
                type, severity, priority, description, latitude, longitude,
                location_name, status, source, transcript, ai_summary, details,
                ai_processed, ai_error, anonymous_id_sha256, occurred_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("type", "other"),
                data.get("severity", "low"),
                data.get("priority", data.get("severity", "low")),
                data.get("description", ""),
                data.get("latitude"),
                data.get("longitude"),
                data.get("location_name"),
                data.get("status", "pending"),
                data.get("source", "manual"),
                data.get("transcript"),
                data.get("ai_summary"),
                details,
                1 if data.get("ai_processed") else 0,
                data.get("ai_error"),
                data.get("anonymous_id_sha256"),
                data.get("occurred_at") or now,
                now,
            ),
        )
        report_id = cursor.lastrowid
    return get_report(report_id)


def get_report(report_id: int) -> dict | None:
    with connection() as conn:
        row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    return report_from_row(row) if row else None


def list_reports(
    report_type: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 200,
) -> list[dict]:
    sql = "SELECT * FROM reports WHERE 1 = 1"
    params: list = []
    if report_type:
        sql += " AND type = ?"
        params.append(report_type)
    if status:
        sql += " AND status = ?"
        params.append(status)
    if search:
        sql += " AND (description LIKE ? OR location_name LIKE ? OR ai_summary LIKE ?)"
        value = f"%{search.strip()}%"
        params.extend([value, value, value])
    sql += " ORDER BY occurred_at DESC, id DESC LIMIT ?"
    params.append(max(1, min(limit, 500)))
    with connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [report_from_row(row) for row in rows]


def update_report_status(report_id: int, status: str) -> dict | None:
    with connection() as conn:
        conn.execute("UPDATE reports SET status = ? WHERE id = ?", (status, report_id))
    return get_report(report_id)


def update_report_location(
    report_id: int,
    latitude: float | None,
    longitude: float | None,
    location_name: str | None = None,
) -> dict | None:
    with connection() as conn:
        if location_name is not None:
            conn.execute(
                "UPDATE reports SET latitude = ?, longitude = ?, location_name = ? WHERE id = ?",
                (latitude, longitude, location_name, report_id),
            )
        else:
            conn.execute(
                "UPDATE reports SET latitude = ?, longitude = ? WHERE id = ?",
                (latitude, longitude, report_id),
            )
    return get_report(report_id)


def delete_report(report_id: int) -> bool:
    with connection() as conn:
        cursor = conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
    return cursor.rowcount > 0


def create_head(data: dict) -> dict:
    with connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO quarter_heads (
                name, wa_number, quarter_name, city, latitude, longitude,
                notes, status, created_at, verified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("name", "").strip(),
                data.get("wa_number", "").strip(),
                data.get("quarter_name", "").strip(),
                data.get("city"),
                data.get("latitude"),
                data.get("longitude"),
                data.get("notes"),
                data.get("status", "pending"),
                utc_now(),
                None,
            ),
        )
        head_id = cursor.lastrowid
    return get_head(head_id)


def get_head(head_id: int) -> dict | None:
    with connection() as conn:
        row = conn.execute("SELECT * FROM quarter_heads WHERE id = ?", (head_id,)).fetchone()
    return head_from_row(row) if row else None


def get_head_raw(head_id: int) -> sqlite3.Row | None:
    with connection() as conn:
        return conn.execute("SELECT * FROM quarter_heads WHERE id = ?", (head_id,)).fetchone()


def list_heads(status: str | None = None) -> list[dict]:
    sql = "SELECT * FROM quarter_heads"
    params: list = []
    if status:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY created_at DESC, id DESC LIMIT 200"
    with connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [head_from_row(row) for row in rows]


def set_head_status(head_id: int, status: str) -> dict | None:
    verified_at = utc_now() if status == "verified" else None
    with connection() as conn:
        conn.execute(
            "UPDATE quarter_heads SET status = ?, verified_at = ? WHERE id = ?",
            (status, verified_at, head_id),
        )
    return get_head(head_id)


def _area_text(report: dict) -> str:
    parts = [
        report.get("location_name") or "",
        report.get("description") or "",
        report.get("ai_summary") or "",
    ]
    details = report.get("details")
    if isinstance(details, dict):
        for key in ("location", "area", "quarter", "city"):
            value = details.get(key)
            if isinstance(value, str):
                parts.append(value)
    return " ".join(part for part in parts if part)


def _norm(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def matching_head_rows(report: dict) -> list[sqlite3.Row]:
    area = _norm(_area_text(report))
    if not area:
        return []
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM quarter_heads WHERE status = 'verified' ORDER BY id LIMIT 200"
        ).fetchall()
    matches = []
    for row in rows:
        quarter = _norm(row["quarter_name"])
        city = _norm(row["city"])
        if quarter and (quarter in area or area in quarter):
            matches.append(row)
        elif city and len(city) >= 3 and (city in area or area in city):
            matches.append(row)
    return matches[:10]


def matching_heads_for_report(report: dict) -> list[dict]:
    return [head_from_row(row) for row in matching_head_rows(report)]


def stats() -> dict:
    with connection() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM reports").fetchone()["n"]
        pending = conn.execute(
            "SELECT COUNT(*) AS n FROM reports WHERE status = 'pending'"
        ).fetchone()["n"]
        high = conn.execute(
            "SELECT COUNT(*) AS n FROM reports WHERE priority = 'high'"
        ).fetchone()["n"]
        heads = conn.execute(
            "SELECT COUNT(*) AS n FROM quarter_heads WHERE status = 'verified'"
        ).fetchone()["n"]
        applications = conn.execute(
            "SELECT COUNT(*) AS n FROM quarter_heads WHERE status = 'pending'"
        ).fetchone()["n"]
    return {
        "total_reports": total,
        "pending_reports": pending,
        "high_priority": high,
        "verified_heads": heads,
        "pending_heads": applications,
    }
