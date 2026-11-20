import unittest
from fastapi import HTTPException
from app.routes import auth
class RetiredRegistrationTests(unittest.TestCase):
    def test_password_registration_requires_google(self):
        with self.assertRaises(HTTPException) as error:
            auth.register()
        self.assertEqual(error.exception.status_code, 400)
    def test_old_email_links_are_rejected(self):
        with self.assertRaises(HTTPException) as error:
            auth.retired_email_links()
        self.assertEqual(error.exception.status_code, 410)
