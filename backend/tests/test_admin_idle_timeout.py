import asyncio
import unittest
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.config import ADMIN_SESSION_IDLE_TIMEOUT_MINUTES
from app.models import Base, User, UserSession
from app.routes import auth


class AdminIdleTimeoutTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(totp_secret='test-enrolled-secret',
            email="admin@example.com",
            username="admin",
            role="admin",
            is_active=True,
        )
        self.db.add(self.user)
        self.db.commit()
        self.request = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 1)})
        self.tokens = auth._issue_login(self.user, self.db, request=self.request)
        self.session = self.db.query(UserSession).filter_by(user_id=self.user.id).one()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_idle_admin_request_revokes_session(self):
        self.session.last_used_at = datetime.utcnow() - timedelta(
            minutes=ADMIN_SESSION_IDLE_TIMEOUT_MINUTES + 1
        )
        self.db.commit()

        with self.assertRaises(HTTPException) as error:
            asyncio.run(auth.get_current_user(
                self.request,
                token=self.tokens["access_token"],
                db=self.db,
            ))

        self.assertEqual(error.exception.status_code, 401)
        self.assertIsNotNone(self.session.revoked_at)

    def test_active_admin_request_updates_last_activity(self):
        earlier_activity = datetime.utcnow() - timedelta(minutes=2)
        self.session.last_used_at = earlier_activity
        self.db.commit()

        asyncio.run(auth.get_current_user(
            self.request,
            token=self.tokens["access_token"],
            db=self.db,
        ))

        self.assertGreater(self.session.last_used_at, earlier_activity)

    def test_idle_admin_cannot_refresh_session(self):
        self.session.last_used_at = datetime.utcnow() - timedelta(
            minutes=ADMIN_SESSION_IDLE_TIMEOUT_MINUTES + 1
        )
        self.db.commit()

        with self.assertRaises(HTTPException) as error:
            auth.refresh_token(
                auth.RefreshRequest(refresh_token=self.tokens["refresh_token"]),
                self.request,
                self.db,
            )

        self.assertEqual(error.exception.status_code, 401)
        self.assertIsNotNone(self.session.revoked_at)


if __name__ == "__main__":
    unittest.main()
