"""SQLite storage for local public COLA ETL metadata.

The database is a local index only. It stores public registry metadata, raw
artifact paths, parsed JSON paths, and attachment metadata. Label images remain
on disk under ``data/work/public-cola/raw/images``.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from cola_etl.paths import PUBLIC_COLA_DB_PATH, ensure_public_cola_work_dirs


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS registry_records (
    ttb_id TEXT PRIMARY KEY,
    permit_no TEXT,
    serial_number TEXT,
    completed_date TEXT,
    fanciful_name TEXT,
    brand_name TEXT,
    origin TEXT,
    origin_desc TEXT,
    class_type TEXT,
    class_type_desc TEXT,
    source_csv TEXT,
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS form_fetches (
    ttb_id TEXT PRIMARY KEY,
    detail_url TEXT NOT NULL,
    raw_html_path TEXT,
    fetched_at TEXT,
    http_status INTEGER,
    parse_status TEXT NOT NULL DEFAULT 'pending',
    parsed_json_path TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ttb_id TEXT NOT NULL,
    panel_order INTEGER NOT NULL,
    filename TEXT,
    source_url TEXT NOT NULL,
    raw_image_path TEXT,
    image_type TEXT,
    width_inches REAL,
    height_inches REAL,
    alt_text TEXT,
    downloaded_at TEXT,
    http_status INTEGER,
    UNIQUE (ttb_id, panel_order)
);

CREATE INDEX IF NOT EXISTS idx_registry_records_completed_date
ON registry_records(completed_date);

CREATE INDEX IF NOT EXISTS idx_registry_records_origin_desc
ON registry_records(origin_desc);

CREATE INDEX IF NOT EXISTS idx_registry_records_class_type_desc
ON registry_records(class_type_desc);

CREATE INDEX IF NOT EXISTS idx_form_fetches_parse_status
ON form_fetches(parse_status);

CREATE INDEX IF NOT EXISTS idx_attachments_ttb_id
ON attachments(ttb_id);
"""


def utc_now() -> str:
    """Return a compact UTC timestamp for ETL metadata."""

    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def connect(db_path: Path = PUBLIC_COLA_DB_PATH) -> sqlite3.Connection:
    """Open the local ETL database and ensure the schema exists."""

    ensure_public_cola_work_dirs()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA_SQL)
    connection.commit()
    return connection


def upsert_registry_record(
    connection: sqlite3.Connection,
    record: dict[str, str],
    source_csv: str,
) -> None:
    """Insert or update one public registry search-result row."""

    connection.execute(
        """
        INSERT INTO registry_records (
            ttb_id,
            permit_no,
            serial_number,
            completed_date,
            fanciful_name,
            brand_name,
            origin,
            origin_desc,
            class_type,
            class_type_desc,
            source_csv,
            imported_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ttb_id) DO UPDATE SET
            permit_no = excluded.permit_no,
            serial_number = excluded.serial_number,
            completed_date = excluded.completed_date,
            fanciful_name = excluded.fanciful_name,
            brand_name = excluded.brand_name,
            origin = excluded.origin,
            origin_desc = excluded.origin_desc,
            class_type = excluded.class_type,
            class_type_desc = excluded.class_type_desc,
            source_csv = excluded.source_csv,
            imported_at = excluded.imported_at
        """,
        (
            record.get("ttb_id", ""),
            record.get("permit_no", ""),
            record.get("serial_number", ""),
            record.get("completed_date", ""),
            record.get("fanciful_name", ""),
            record.get("brand_name", ""),
            record.get("origin", ""),
            record.get("origin_desc", ""),
            record.get("class_type", ""),
            record.get("class_type_desc", ""),
            source_csv,
            utc_now(),
        ),
    )


def list_ttb_ids(
    connection: sqlite3.Connection,
    *,
    explicit_ids: Iterable[str] | None = None,
    missing_forms_only: bool = False,
    limit: int | None = None,
) -> list[str]:
    """Return TTB IDs from explicit input or the local registry table."""

    if explicit_ids:
        ids = [ttb_id.strip() for ttb_id in explicit_ids if ttb_id.strip()]
        return ids[:limit] if limit else ids

    if missing_forms_only:
        rows = connection.execute(
            """
            SELECT r.ttb_id
            FROM registry_records r
            LEFT JOIN form_fetches f ON f.ttb_id = r.ttb_id
            WHERE f.raw_html_path IS NULL
            ORDER BY r.completed_date DESC, r.ttb_id
            LIMIT COALESCE(?, -1)
            """,
            (limit,),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT ttb_id
            FROM registry_records
            ORDER BY completed_date DESC, ttb_id
            LIMIT COALESCE(?, -1)
            """,
            (limit,),
        ).fetchall()

    return [row["ttb_id"] for row in rows]


def record_form_fetch(
    connection: sqlite3.Connection,
    *,
    ttb_id: str,
    detail_url: str,
    raw_html_path: str | None,
    http_status: int | None,
    error: str | None = None,
) -> None:
    """Record the result of a public form fetch attempt."""

    connection.execute(
        """
        INSERT INTO form_fetches (
            ttb_id, detail_url, raw_html_path, fetched_at, http_status, error
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(ttb_id) DO UPDATE SET
            detail_url = excluded.detail_url,
            raw_html_path = excluded.raw_html_path,
            fetched_at = excluded.fetched_at,
            http_status = excluded.http_status,
            error = excluded.error
        """,
        (ttb_id, detail_url, raw_html_path, utc_now(), http_status, error),
    )


def record_parsed_form(
    connection: sqlite3.Connection,
    *,
    ttb_id: str,
    parsed_json_path: str | None,
    parse_status: str,
    error: str | None = None,
) -> None:
    """Record the result of parsing a public COLA form HTML file."""

    connection.execute(
        """
        INSERT INTO form_fetches (
            ttb_id, detail_url, parse_status, parsed_json_path, error
        )
        VALUES (?, '', ?, ?, ?)
        ON CONFLICT(ttb_id) DO UPDATE SET
            parse_status = excluded.parse_status,
            parsed_json_path = excluded.parsed_json_path,
            error = excluded.error
        """,
        (ttb_id, parse_status, parsed_json_path, error),
    )


def replace_attachments(
    connection: sqlite3.Connection,
    *,
    ttb_id: str,
    attachments: list[dict],
) -> None:
    """Replace parsed attachment metadata for one TTB ID."""

    connection.execute("DELETE FROM attachments WHERE ttb_id = ?", (ttb_id,))
    for attachment in attachments:
        connection.execute(
            """
            INSERT INTO attachments (
                ttb_id,
                panel_order,
                filename,
                source_url,
                image_type,
                width_inches,
                height_inches,
                alt_text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ttb_id,
                attachment.get("panel_order"),
                attachment.get("filename"),
                attachment.get("source_url"),
                attachment.get("image_type"),
                attachment.get("width_inches"),
                attachment.get("height_inches"),
                attachment.get("alt_text"),
            ),
        )


def pending_attachments(
    connection: sqlite3.Connection,
    *,
    explicit_ids: Iterable[str] | None = None,
    missing_only: bool = True,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    """Return attachment rows that can be downloaded."""

    clauses: list[str] = []
    params: list[object] = []
    ids = [ttb_id.strip() for ttb_id in explicit_ids or [] if ttb_id.strip()]

    if ids:
        placeholders = ",".join("?" for _ in ids)
        clauses.append(f"ttb_id IN ({placeholders})")
        params.extend(ids)
    if missing_only:
        clauses.append("(raw_image_path IS NULL OR raw_image_path = '')")
        clauses.append("http_status IS NULL")

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    limit_sql = "LIMIT ?" if limit else ""
    if limit:
        params.append(limit)

    return connection.execute(
        f"""
        SELECT *
        FROM attachments
        {where_sql}
        ORDER BY ttb_id, panel_order
        {limit_sql}
        """,
        params,
    ).fetchall()


def record_attachment_download(
    connection: sqlite3.Connection,
    *,
    attachment_id: int,
    raw_image_path: str | None,
    http_status: int | None,
) -> None:
    """Record a downloaded label image path and status."""

    connection.execute(
        """
        UPDATE attachments
        SET raw_image_path = ?, http_status = ?, downloaded_at = ?
        WHERE id = ?
        """,
        (raw_image_path, http_status, utc_now(), attachment_id),
    )
