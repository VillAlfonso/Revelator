import unittest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models import Base, User, Scan, OperationalEvent, AccountArchiveEvent, AdminAuditLog
from app.routes.admin import archive_account_history


class ArchiveHistoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(email='archived@example.com', username='archived', is_active=False, archived_at=datetime.utcnow())
        self.other = User(email='other@example.com', username='other')
        self.db.add_all([self.user, self.other]); self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def history(self, kind, offset=0):
        return archive_account_history(self.user.id, self.other, self.db, kind, 25, offset)

    def test_all_scans_are_paginated_without_mixing_accounts(self):
        for n in range(27):
            self.db.add(Scan(user_id=self.user.id, scan_id=f'scan-{n}', filename=f'{n}.jpg', verdict='forged', confidence_score=.9, category_evidence='["visible evidence"]'))
        self.db.add(Scan(user_id=self.other.id, scan_id='private', filename='private.jpg', verdict='forged', confidence_score=.9))
        self.db.commit()
        first, last = self.history('scans'), self.history('scans', 25)
        self.assertEqual(first['total'], 27)
        self.assertEqual(len(first['items']), 25)
        self.assertEqual(len(last['items']), 2)
        self.assertNotIn('private', {row['scan']['scan_id'] for row in first['items'] + last['items']})
        self.assertEqual(first['items'][0]['scan']['category_evidence'], ['visible evidence'])
        self.assertNotIn('hashed_password', first['account'])

    def test_errors_and_actions_belong_to_selected_account(self):
        self.db.add_all([
            OperationalEvent(user_id=self.user.id, event_type='scan_failed', severity='error', message='Failed'),
            OperationalEvent(user_id=self.other.id, event_type='scan_failed', severity='error', message='Other user'),
            AdminAuditLog(admin_id=self.other.id, target_user_id=self.user.id, action='ban_user', details='{"reason":"test"}'),
        ])
        self.db.commit()
        self.assertEqual(self.history('errors')['total'], 1)
        self.assertEqual(self.history('actions')['total'], 1)

    def test_original_identity_remains_available_after_reregistration(self):
        self.db.add(AccountArchiveEvent(user_id=self.user.id, email=self.user.email, action='archived', snapshot='{"email":"archived@example.com","username":"original"}'))
        self.user.email = f'archived-{self.user.id}@archive.invalid'
        self.db.commit()
        result = self.history('archive')
        self.assertEqual(result['account']['email'], 'archived@example.com')
        self.assertEqual(result['account']['username'], 'original')
        self.assertEqual(result['total'], 1)

    def test_active_or_missing_accounts_are_not_archive_entries(self):
        for user_id in (self.other.id, 'missing'):
            with self.assertRaises(HTTPException) as error:
                archive_account_history(user_id, self.other, self.db, 'scans', 25, 0)
            self.assertEqual(error.exception.status_code, 404)
