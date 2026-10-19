import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request
from app.models import Base, User, RegistrationCode
from app.routes import auth

class RegistrationOTPTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:'); Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.request = Request({'type': 'http', 'headers': [], 'client': ('127.0.0.1', 1)})
        self.body = auth.RegisterRequest(email='new@gmail.com', username='newuser', password='Password12345')
        self.mail = patch.object(auth, 'send_registration_code_email', return_value=True).start()
        patch.object(auth, 'enforce_rate_limit').start()
    def tearDown(self):
        patch.stopall(); self.db.close(); self.engine.dispose()
    def start(self):
        result = auth.register(self.body, self.request, self.db)
        self.assertNotIn('access_token', result)
        self.assertEqual(self.db.query(User).count(), 0)
        return self.mail.call_args.args[1]
    def verify(self, code):
        return auth.verify_registration(auth.VerifyRegistrationRequest(email=self.body.email, code=code), self.request, self.db)
    def test_valid_code_creates_account_once(self):
        code = self.start()
        self.assertIn('access_token', self.verify(code))
        with self.assertRaises(HTTPException): self.verify(code)
    def test_five_wrong_attempts_lock_code(self):
        code = self.start()
        wrong = '000000' if code != '000000' else '111111'
        for _ in range(5):
            with self.assertRaises(HTTPException): self.verify(wrong)
        with self.assertRaises(HTTPException): self.verify(code)
    def test_expired_code(self):
        code = self.start()
        self.db.query(RegistrationCode).one().expires_at = datetime.utcnow() - timedelta(seconds=1)
        self.db.commit()
        with self.assertRaises(HTTPException): self.verify(code)
    def test_resend_invalidates_previous_code(self):
        with patch.object(auth, 'generate_otp_code', side_effect=['123456', '654321']):
            self.start(); self.start()
        with self.assertRaises(HTTPException): self.verify('123456')
        self.assertIn('access_token', self.verify('654321'))
    def test_delivery_failure_does_not_create_account(self):
        self.mail.return_value = False
        with self.assertRaises(HTTPException): auth.register(self.body, self.request, self.db)
        self.assertEqual(self.db.query(User).count(), 0)
        self.assertEqual(self.db.query(RegistrationCode).count(), 0)
