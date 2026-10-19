# Authenticator and account archive rollout

Restart the backend after installing backend/requirements.txt, then refresh the built frontend.
The startup migration creates the new tables/columns and invalidates existing sessions once.
Existing users keep their accounts and can authenticate with their previous password or Google identity.
They must complete Google Authenticator enrollment before receiving a new session.

New accounts require Google-verified email and Google Workspace hosted domain lspu.edu.ph.
Typed-email registration and SMTP verification/reset endpoints are disabled.
Authenticator setup QR codes are generated locally; secrets are encrypted with the existing key encryption configuration.
Keep API_KEY_ENCRYPTION_KEY (or its existing SECRET_KEY fallback) stable and backed up.
Ten recovery codes are shown once after enrollment. Store them safely.
Account recovery consumes a recovery code, changes the password, invalidates all sessions and remaining codes,
and requires fresh Authenticator enrollment. Existing Google users can also set a password through this flow.
A super administrator can reset Authenticator only after independently verifying the person's identity;
the interface requires an explanation and records the action. It cannot reset the administrator's own account.

Archive replaces both administrator deletion and self-service deletion.
Data is retained, access is disabled, and the archive event is recorded separately without credentials.
An eligible archived institutional identity can register again: its old account data remains archived under
the old user ID, the new account is a regular user with a fresh ID, and the event history remains.
Banned accounts cannot register again until a super administrator lifts the ban.
The Archive tab lists current archived/banned identities and the latest 100 permanent history events.
Previously physically deleted accounts cannot be retroactively recovered by this change.

The Git history integration uses the ours merge strategy intentionally: it includes existing branch
commit ancestry while keeping the current application tree. It does not rewrite commit authors or dates.
GitHub controls contribution attribution and when its graph refreshes.
