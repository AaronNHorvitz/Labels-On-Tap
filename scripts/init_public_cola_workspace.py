#!/usr/bin/env python
"""Create the local public COLA ETL workspace and SQLite database."""

from __future__ import annotations

from cola_etl.database import connect
from cola_etl.paths import PUBLIC_COLA_DB_PATH, ensure_public_cola_work_dirs


def main() -> None:
    """Initialize local ETL directories and database schema."""

    ensure_public_cola_work_dirs()
    with connect() as connection:
        connection.commit()
    print(f"Initialized public COLA workspace at {PUBLIC_COLA_DB_PATH.parent}")
    print(f"SQLite database: {PUBLIC_COLA_DB_PATH}")


if __name__ == "__main__":
    main()
