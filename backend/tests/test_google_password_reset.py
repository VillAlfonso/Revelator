import unittest
from fastapi import HTTPException
from app.routes import auth
class RetiredEmailResetTests(unittest.TestCase):
    def test_email_code_resend_is_disabled(self):
        with self.assertRaises(HTTPException) as error:
            auth.no_email_verification()
        self.assertEqual(error.exception.status_code, 400)
