import unittest
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request
from app.models import Base, User, UserSession
from app.routes import auth
from app.device_details import device_label
from app import database
from sqlalchemy import text


class DeviceSessionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(email='test@example.com', username='test', is_active=True, totp_secret='test-enrolled-secret')
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def request(self, browser=None):
        return Request({'type': 'http', 'headers': [
            (b'x-browser-id', (browser or str(uuid4())).encode()),
            (b'user-agent', b'Mozilla/5.0 (Windows NT 10.0) Chrome/155.0')],
            'client': ('192.0.2.1', 1234)})

    def active(self):
        return self.db.query(UserSession).filter(UserSession.revoked_at.is_(None)).all()

    def test_repeat_login_replaces_only_same_account_browser(self):
        request = self.request()
        auth._issue_login(self.user, self.db, request=request)
        auth._issue_login(self.user, self.db, request=self.request())
        auth._issue_login(self.user, self.db, request=request)
        self.assertEqual(len(self.active()), 2)
        other = User(email='other@example.com', username='other')
        self.db.add(other)
        self.db.commit()
        auth._issue_login(other, self.db, request=request)
        self.assertEqual(len(self.active()), 3)

    def test_refresh_preserves_browser_and_location(self):
        request = self.request()
        tokens = auth._issue_login(self.user, self.db, request=request)
        old = self.active()[0]
        old.location = '1.23, 4.56'
        self.db.commit()
        auth.refresh_token(auth.RefreshRequest(refresh_token=tokens['refresh_token']), request, self.db)
        self.assertEqual(len(self.active()), 1)
        new = self.active()[0]
        self.assertEqual(new.browser_id, old.browser_id)
        self.assertEqual(new.location, old.location)
        self.assertEqual(new.ip_address, '192.0.2.1')
        self.assertEqual(device_label(new.label), 'Windows PC · Chrome')

    def test_missing_id_does_not_merge_unrelated_devices(self):
        auth._issue_login(self.user, self.db)
        auth._issue_login(self.user, self.db)
        self.assertEqual(len(self.active()), 2)

    def test_mobile_labels(self):
        self.assertEqual(device_label('iPhone Safari/600'), 'iPhone · Safari')
        self.assertEqual(device_label('Android Mobile Chrome/1'), 'Android phone · Chrome')

    def test_legacy_cleanup_runs_once(self):
        with self.engine.begin() as conn:
            conn.execute(text('DROP TABLE user_sessions'))
            conn.execute(text('CREATE TABLE user_sessions (id VARCHAR, revoked_at DATETIME)'))
            conn.execute(text("INSERT INTO user_sessions (id) VALUES ('legacy')"))
        with patch.object(database, 'engine', self.engine):
            database._ensure_columns()
            database._ensure_columns()
        self.db.expire_all()
        self.assertEqual(self.user.auth_version, 1)
        with self.engine.connect() as conn:
            self.assertIsNotNone(conn.execute(text('SELECT revoked_at FROM user_sessions')).scalar())

    def test_location_is_limited_to_current_session_and_can_be_removed(self):
        request = self.request()
        tokens = auth._issue_login(self.user, self.db, request=request)
        request.scope['headers'].append((b'authorization', f"Bearer {tokens['access_token']}".encode()))
        auth.update_session_location(auth.SessionLocationRequest(latitude=1.23456, longitude=103.87654),
                                     request, self.user, self.db)
        self.assertEqual(self.active()[0].location, '1.23, 103.88')
        auth.update_session_location(auth.SessionLocationRequest(), request, self.user, self.db)
        self.assertIsNone(self.active()[0].location)


if __name__ == '__main__':
    unittest.main()
