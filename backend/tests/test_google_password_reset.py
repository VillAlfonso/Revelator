import unittest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request
from fastapi import HTTPException
from app.models import Base, User
from app.routes import auth
class EmailPasswordResetTests(unittest.TestCase):
    def test_google_account_can_set_password_with_single_use_emailed_link(self):
        engine = create_engine('sqlite:///:memory:'); Base.metadata.create_all(engine)
        request = Request({'type': 'http', 'headers': [], 'client': ('127.0.0.1', 1)})
        with Session(engine) as db, patch.object(auth, 'enforce_rate_limit'), patch.object(auth, 'send_reset_email', return_value=True) as send:
            user = User(email='google@gmail.com', username='google', google_id='google-id', is_verified=True)
            db.add(user); db.commit()
            auth.forgot_password(auth.ForgotPasswordRequest(email=user.email), request, db)
            token = send.call_args.args[1]
            body = auth.ResetPasswordRequest(token=token, password='NewPassword12345')
            auth.reset_password(body, request, db)
            self.assertTrue(auth.verify_password(body.password, user.hashed_password))
            with self.assertRaises(HTTPException): auth.reset_password(body, request, db)
        engine.dispose()
