import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, User
from app.routes import auth


class AccountDeletionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.owner = User(email='owner@example.com', username='owner')
        self.other = User(email='other@example.com', username='other')
        self.db.add_all([self.owner, self.other])
        self.db.commit()
        self.uploads = tempfile.TemporaryDirectory()
        self.patch = patch.object(auth, 'UPLOAD_DIR', Path(self.uploads.name))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.uploads.cleanup()
        self.db.close()
        self.engine.dispose()

    def test_other_email_is_rejected_without_deleting_either_account(self):
        with self.assertRaises(HTTPException) as error:
            auth.delete_my_account(
                auth.DeleteAccountRequest(email=self.other.email, confirmation='ARCHIVE'),
                self.owner, self.db,
            )
        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(self.db.query(User).count(), 2)

    def test_matching_email_deletes_only_authenticated_account(self):
        owner_id, other_id = self.owner.id, self.other.id
        result = auth.delete_my_account(
            auth.DeleteAccountRequest(email=self.owner.email, confirmation='ARCHIVE'),
            self.owner, self.db,
        )
        self.assertTrue(result['success'])
        self.assertIsNotNone(self.db.get(User, owner_id).archived_at)
        self.assertFalse(self.db.get(User, owner_id).is_active)
        self.assertIsNotNone(self.db.get(User, other_id))


if __name__ == '__main__':
    unittest.main()
