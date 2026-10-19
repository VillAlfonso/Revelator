import unittest
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request
from app.models import Base, User, AccountArchiveEvent
from app.account_security import archive_account
from app.routes import auth

class RestoredAuthArchiveTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:'); Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(email='old@gmail.com', username='old', google_id='google-id', is_verified=True, hashed_password=auth.hash_password('Password12345'))
        self.db.add(self.user); self.db.commit()
        self.request = Request({'type': 'http', 'headers': [], 'client': ('127.0.0.1', 1)})
        patch.object(auth, 'enforce_rate_limit').start()
    def tearDown(self):
        patch.stopall(); self.db.close(); self.engine.dispose()
    def google(self):
        with patch.object(auth, 'GOOGLE_CLIENT_ID', 'test'), patch('google.oauth2.id_token.verify_oauth2_token', return_value={
            'email': 'old@gmail.com', 'sub': 'google-id', 'email_verified': True}):
            return auth.google_login(auth.GoogleAuthRequest(id_token='test'), self.request, self.db)
    def test_google_signin_does_not_require_authenticator(self):
        result = self.google()
        self.assertIn('access_token', result)
        self.assertNotIn('challenge_token', result)
    def test_password_signin_emails_code(self):
        with patch.object(auth, '_smtp_configured', return_value=True), patch.object(auth, 'send_2fa_code_email', return_value=True) as send:
            result = auth.login(auth.LoginRequest(email=self.user.email, password='Password12345'), self.request, self.db)
            self.assertTrue(result['requires_2fa'])
            self.assertNotIn('access_token', result)
            code = send.call_args.args[1]
            result = auth.verify_2fa(auth.Verify2FARequest(email=self.user.email, code=code), self.request, self.db)
            self.assertIn('access_token', result)
    def test_banned_user_cannot_signin_or_register(self):
        self.user.is_active = False; self.db.commit()
        with self.assertRaises(HTTPException): self.google()
        with self.assertRaises(HTTPException): auth.register(auth.RegisterRequest(email=self.user.email, username='fresh', password='Password12345'), self.request, self.db)
    def test_archived_google_user_gets_fresh_account_and_keeps_history(self):
        old_id = self.user.id
        archive_account(self.user, self.db)
        result = self.google()
        self.assertNotEqual(result['user']['id'], old_id)
        self.assertIsNotNone(self.db.get(User, old_id).archived_at)
        self.assertEqual(self.db.query(AccountArchiveEvent).count(), 2)
