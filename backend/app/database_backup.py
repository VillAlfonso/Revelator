"""Create consistent SQLite snapshots without copying a live database file."""
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path


def create_database_backup(engine):
    if engine.dialect.name != "sqlite":
        raise ValueError("Database backup download currently supports SQLite only.")
    with tempfile.NamedTemporaryFile(prefix="revelator-backup-", suffix=".sqlite3", delete=False) as temp:
        path = Path(temp.name)
    source = None
    try:
        source = engine.raw_connection()
        with closing(sqlite3.connect(path)) as destination:
            source.driver_connection.backup(destination, pages=256, sleep=0.05)
            if destination.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise RuntimeError("Backup integrity check failed")
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        if source is not None:
            source.close()
