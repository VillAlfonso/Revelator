import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
import pyotp
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request
from app.models import Base, User, AuthChallenge, RecoveryCode, AccountArchiveEvent
from app.account_security import begin_auth, finish_auth, archive_account
from app.routes import auth

class AuthenticatorArchiveTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(email='legacy@gmail.com', username='legacy', is_verified=True,
                         hashed_password=auth.hash_password('Password12345'))
        self.db.add(self.user); self.db.commit()
        self.request = Request({'type': 'http', 'headers': [], 'client': ('127.0.0.1', 1)})
        patch.object(auth, 'enforce_rate_limit').start()
    def tearDown(self):
        patch.stopall(); self.db.close(); self.engine.dispose()
    def enroll(self):
        challenge = begin_auth(self.user, self.db)
        user, codes = finish_auth(challenge['challenge_token'], pyotp.TOTP(challenge['setup_key']).now(), self.db)
        return challenge, codes
    def google(self, email, sub='google-id', hd='lspu.edu.ph', verified=True):
        with patch.object(auth, 'GOOGLE_CLIENT_ID', 'test'), patch('google.oauth2.id_token.verify_oauth2_token', return_value={
            'email': email, 'sub': sub, 'hd': hd, 'email_verified': verified, 'name': 'Test'}):
            return auth.google_login(auth.GoogleAuthRequest(id_token='test'), self.request, self.db)
    def test_legacy_password_requires_setup_without_session(self):
        result = auth.login(auth.LoginRequest(email=self.user.email, password='Password12345'), self.request, self.db)
        self.assertTrue(result['setup_required']); self.assertNotIn('access_token', result)
    def test_setup_encrypts_secret_and_issues_hashed_recovery_codes(self):
        challenge, codes = self.enroll()
        self.assertTrue(self.user.totp_secret.startswith('enc:'))
        self.assertNotEqual(self.user.totp_secret, challenge['setup_key'])
        self.assertEqual(len(codes), 10)
        self.assertNotIn(codes[0], [c.code_hash for c in self.db.query(RecoveryCode)])
    def test_challenge_and_totp_replay_rejected(self):
        challenge, codes = self.enroll()
        with self.assertRaises(HTTPException):
            finish_auth(challenge['challenge_token'], pyotp.TOTP(challenge['setup_key']).now(), self.db)
        new = begin_auth(self.user, self.db)
        with self.assertRaises(HTTPException):
            finish_auth(new['challenge_token'], pyotp.TOTP(challenge['setup_key']).now(), self.db)
        finish_auth(new['challenge_token'], codes[0], self.db)
        again = begin_auth(self.user, self.db)
        with self.assertRaises(HTTPException): finish_auth(again['challenge_token'], codes[0], self.db)
    def test_expired_and_locked_challenges(self):
        challenge = begin_auth(self.user, self.db)
        row = self.db.query(AuthChallenge).one(); row.expires_at = datetime.utcnow() - timedelta(seconds=1); self.db.commit()
        with self.assertRaises(HTTPException): finish_auth(challenge['challenge_token'], '000000', self.db)
        challenge = begin_auth(self.user, self.db)
        for _ in range(5):
            with self.assertRaises(HTTPException): finish_auth(challenge['challenge_token'], 'invalid', self.db)
        with self.assertRaises(HTTPException): finish_auth(challenge['challenge_token'], pyotp.TOTP(challenge['setup_key']).now(), self.db)
    def test_recovery_resets_password_and_requires_new_enrollment(self):
        _, codes = self.enroll()
        result = auth.recover_account(auth.RecoverAccountRequest(email=self.user.email, recovery_code=codes[0], password='ChangedPassword123'), self.request, self.db)
        self.assertTrue(result['setup_required']); self.assertNotIn('access_token', result)
        self.assertTrue(auth.verify_password('ChangedPassword123', self.user.hashed_password))
        self.assertEqual(self.db.query(RecoveryCode).count(), 0)
    def test_new_google_domain_and_verified_claim_required(self):
        for email, hd, verified in [('new@gmail.com', None, True), ('new@lspu.edu.ph', None, True), ('new@lspu.edu.ph', 'lspu.edu.ph', False)]:
            with self.assertRaises(HTTPException): self.google(email, hd=hd, verified=verified)
        self.assertTrue(self.google('new@lspu.edu.ph')['setup_required'])
    def test_existing_google_account_keeps_legacy_domain_access(self):
        self.assertTrue(self.google(self.user.email, hd=None)['setup_required'])
    def test_ban_cannot_be_bypassed_or_archived(self):
        self.user.is_active = False; self.db.commit()
        with self.assertRaises(HTTPException): self.google(self.user.email, hd=None)
        with self.assertRaises(HTTPException): archive_account(self.user, self.db)
    def test_archive_reregistration_preserves_original_and_history(self):
        self.user.email = 'old@lspu.edu.ph'; self.user.google_id = 'google-id'; self.db.commit()
        old_id = self.user.id
        archive_account(self.user, self.db)
        self.google('old@lspu.edu.ph')
        new = self.db.query(User).filter(User.email == 'old@lspu.edu.ph').one()
        self.assertNotEqual(new.id, old_id)
        self.assertIsNotNone(self.db.get(User, old_id).archived_at)
        self.assertEqual(self.db.query(AccountArchiveEvent).count(), 2)
    def test_archived_noninstitutional_cannot_register_again(self):
        archive_account(self.user, self.db)
        with self.assertRaises(HTTPException): self.google(self.user.email, hd=None)
    def test_invalid_recovery_does_not_change_password(self):
        self.enroll()
        original = self.user.hashed_password
        with self.assertRaises(HTTPException):
            auth.recover_account(auth.RecoverAccountRequest(email=self.user.email,
                recovery_code='invalid-code', password='ChangedPassword123'), self.request, self.db)
        self.assertEqual(self.user.hashed_password, original)
        self.assertEqual(self.db.query(RecoveryCode).count(), 10)
    def test_archival_invalidates_pending_challenge(self):
        challenge = begin_auth(self.user, self.db)
        archive_account(self.user, self.db)
        with self.assertRaises(HTTPException):
            finish_auth(challenge['challenge_token'], pyotp.TOTP(challenge['setup_key']).now(), self.db)
    def test_authenticator_required_for_existing_access_token(self):
        from app.auth import get_user_from_token, create_access_token
        with self.assertRaises(HTTPException):
            get_user_from_token(create_access_token(self.user.id, auth_version=self.user.auth_version), self.db)
    def test_admin_reset_requires_other_account_and_revokes_codes(self):
        from app.routes import admin
        self.enroll()
        operator = User(email='operator@gmail.com', username='operator', role='superadmin')
        self.db.add(operator); self.db.commit()
        with self.assertRaises(HTTPException):
            admin.reset_authenticator(operator.id, admin.AssistanceRequest(reason='Verified identity in person'), operator, self.db)
        admin.reset_authenticator(self.user.id, admin.AssistanceRequest(reason='Verified identity in person'), operator, self.db)
        self.assertIsNone(self.user.totp_secret)
        self.assertEqual(self.db.query(RecoveryCode).count(), 0)
