# Authentication rollback and account archive

Authentication has been restored to the email OTP flow:
- Email/password registration creates an account only after a six-digit emailed code is verified.
- Sign-in uses the previous email-code two-factor and remembered-browser behavior.
- Google sign-in works without Authenticator enrollment or a new institutional-domain restriction.
- Password recovery uses a single-use emailed link, including for Google-only accounts.
- The forgot-password email comes from the sign-in form.

Authenticator setup, app-code verification, recovery-code login, and admin Authenticator reset are disabled.
Dormant database columns are retained to avoid destructive migration; they do not gate access.
Restart the backend and refresh the rebuilt frontend to activate the rollback. SMTP settings are unchanged.

Archive remains enabled for both self-service and administrator account removal.
Archived data and permanent history remain, while eligible re-registration gets a fresh account.
Banned accounts cannot sign in or register again until the ban is lifted.
The previous history-only Git merge remains intact.
