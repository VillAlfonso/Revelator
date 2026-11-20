import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.database_backup import create_database_backup
from app.routes.admin import download_database_backup
from app.models import User
from app.auth import get_current_user
from app.database import get_db
from fastapi import BackgroundTasks


class DatabaseBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine('sqlite:///' + (Path(self.temp.name) / 'source.db').as_posix())
        with self.engine.begin() as conn:
            conn.execute(text('PRAGMA journal_mode=WAL'))
            conn.execute(text('CREATE TABLE example (value TEXT)'))
            conn.execute(text("INSERT INTO example VALUES ('retained record')"))

    def tearDown(self):
        self.engine.dispose()
        self.temp.cleanup()

    def test_snapshot_contains_committed_data_and_does_not_change_source(self):
        path = create_database_backup(self.engine)
        try:
            connection = sqlite3.connect(path)
            try:
                self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(connection.execute('SELECT value FROM example').fetchone()[0], 'retained record')
            finally:
                connection.close()
            with self.engine.connect() as conn:
                self.assertEqual(conn.execute(text('SELECT count(*) FROM example')).scalar(), 1)
        finally:
            path.unlink()

    def test_download_is_not_cached_and_temporary_file_is_cleaned(self):
        with Session(self.engine) as db:
            tasks = BackgroundTasks()
            response = download_database_backup(tasks, User(role='superadmin'), db)
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertTrue(Path(response.path).exists())
            asyncio.run(tasks())
            self.assertFalse(Path(response.path).exists())

    def test_regular_admin_cannot_download_database(self):
        app = FastAPI()
        app.get('/backup')(download_database_backup)
        app.dependency_overrides[get_current_user] = lambda: User(role='admin')
        def database():
            with Session(self.engine) as db:
                yield db
        app.dependency_overrides[get_db] = database
        with patch('app.database_backup.create_database_backup') as backup:
            response = TestClient(app).get('/backup')
            self.assertEqual(response.status_code, 403)
            backup.assert_not_called()
