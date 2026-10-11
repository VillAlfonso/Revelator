import argparse
import sqlite3
from pathlib import Path


def read_only_connection(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def table_rows(connection: sqlite3.Connection, table: str) -> tuple[list[str], dict[tuple, tuple]]:
    info = list(connection.execute(f'PRAGMA table_info("{table}")'))
    columns = [row[1] for row in info]
    primary_key_indexes = [row[0] for row in info if row[5]]
    if not primary_key_indexes:
        raise ValueError(f"Table {table} has no primary key")

    rows = {}
    for row in connection.execute(f'SELECT * FROM "{table}"'):
        key = tuple(row[index] for index in primary_key_indexes)
        rows[key] = tuple(row)
    return columns, rows


def merge(active_path: Path, snapshot_path: Path, output_path: Path, dry_run: bool) -> None:
    active = read_only_connection(active_path)
    snapshot = read_only_connection(snapshot_path)
    output = None
    try:
        active_tables = table_names(active)
        snapshot_tables = table_names(snapshot)
        if active_tables != snapshot_tables:
            raise ValueError("Database tables differ; refusing to merge")

        table_data = {}
        for table in sorted(active_tables):
            active_info = list(active.execute(f'PRAGMA table_info("{table}")'))
            snapshot_info = list(snapshot.execute(f'PRAGMA table_info("{table}")'))
            if active_info != snapshot_info:
                raise ValueError(f"Schema differs for table {table}; refusing to merge")
            active_columns, active_rows = table_rows(active, table)
            snapshot_columns, snapshot_rows = table_rows(snapshot, table)
            if active_columns != snapshot_columns:
                raise ValueError(f"Columns differ for table {table}; refusing to merge")
            additions = set(snapshot_rows) - set(active_rows)
            changed = sum(
                active_rows[key] != snapshot_rows[key]
                for key in set(active_rows).intersection(snapshot_rows)
            )
            table_data[table] = (active_columns, additions)
            print(f"{table}: active={len(active_rows)}, snapshot={len(snapshot_rows)}, add={len(additions)}, differing shared rows={changed}")

        if dry_run:
            return
        if output_path.exists():
            raise FileExistsError(f"Output already exists: {output_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output = sqlite3.connect(output_path, uri=True)
        active.backup(output)
        output.execute("PRAGMA foreign_keys = ON")
        snapshot_uri = f"file:{snapshot_path.as_posix()}?mode=ro"
        output.execute("ATTACH DATABASE ? AS snapshot", (snapshot_uri,))
        output.execute("BEGIN IMMEDIATE")

        order = [table for table in ("users", "classrooms") if table in active_tables]
        order.extend(sorted(active_tables - set(order)))
        for table in order:
            columns, expected_keys = table_data[table]
            column_list = ", ".join(f'"{column}"' for column in columns)
            before = output.execute(f'SELECT COUNT(*) FROM main."{table}"').fetchone()[0]
            output.execute(
                f'INSERT OR IGNORE INTO main."{table}" ({column_list}) '
                f'SELECT {column_list} FROM snapshot."{table}"'
            )
            after = output.execute(f'SELECT COUNT(*) FROM main."{table}"').fetchone()[0]
            if after - before != len(expected_keys):
                raise ValueError(f"Unexpected uniqueness conflict while merging {table}")

        violations = list(output.execute("PRAGMA foreign_key_check"))
        if violations:
            raise ValueError(f"Merged database has {len(violations)} foreign-key violations")
        output.commit()
        print(f"Merged database written to {output_path}")
    except Exception:
        if output is not None:
            output.rollback()
        raise
    finally:
        if output is not None:
            output.close()
        active.close()
        snapshot.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge a SQLite snapshot into a new database file.")
    parser.add_argument("--active", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    merge(args.active, args.snapshot, args.output, args.dry_run)


if __name__ == "__main__":
    main()