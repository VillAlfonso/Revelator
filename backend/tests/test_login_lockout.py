import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.models import Base, User
from app.routes import auth


class LoginLockoutTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(
            email="user@example.com",
            username="user",
            hashed_password=auth.hash_password("CorrectPassword123"),
            is_active=True,
            is_verified=True,
        )
        self.db.add(self.user)
        self.db.commit()
        self.request = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 1)})
        self.rate_limit_patch = patch.object(auth, "enforce_rate_limit")
        self.rate_limit_patch.start()

    def tearDown(self):
        self.rate_limit_patch.stop()
        self.db.close()
        self.engine.dispose()

    def login(self, password):
        return auth.login(
            auth.LoginRequest(email=self.user.email, password=password),
            self.request,
            self.db,
        )

    def test_third_bad_password_locks_account_and_returns_retry_time(self):
        for _ in range(2):
            with self.assertRaises(HTTPException) as error:
                self.login("wrong")
            self.assertEqual(error.exception.status_code, 401)

        with self.assertRaises(HTTPException) as error:
            self.login("wrong")
        self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(error.exception.headers["Retry-After"], "60")
        self.assertEqual(self.user.failed_login_attempts, 3)
        self.assertGreater(self.user.login_locked_until, datetime.utcnow())

        with self.assertRaises(HTTPException) as error:
            self.login("CorrectPassword123")
        self.assertEqual(error.exception.status_code, 429)

        self.user.login_locked_until = datetime.utcnow() - timedelta(seconds=1)
        self.db.commit()
        with self.assertRaises(HTTPException) as error:
            self.login("wrong")
        self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(error.exception.headers["Retry-After"], "120")
        self.assertEqual(self.user.failed_login_attempts, 4)

        self.user.login_locked_until = datetime.utcnow() - timedelta(seconds=1)
        self.db.commit()
        with self.assertRaises(HTTPException) as error:
            self.login("wrong")
        self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(error.exception.headers["Retry-After"], "180")
        self.assertEqual(self.user.failed_login_attempts, 5)

    def test_expired_lock_allows_login_and_clears_failure_counter(self):
        self.user.failed_login_attempts = 3
        self.user.login_locked_until = datetime.utcnow() - timedelta(seconds=1)
        self.db.commit()

        result = self.login("CorrectPassword123")

        self.assertIn("challenge_token", result)
        self.assertNotIn("access_token", result)
        self.assertEqual(self.user.failed_login_attempts, 0)
        self.assertIsNone(self.user.login_locked_until)
