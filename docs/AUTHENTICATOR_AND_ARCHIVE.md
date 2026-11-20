# Authenticator verification and account archive

## Activation
Restart the backend and refresh the built frontend. Install backend/requirements.txt on other hosts.
Existing accounts and records remain. Users without an enrolled Authenticator must sign in again with
their existing password or Google identity, then enroll before they receive a full login session.
Existing password lockout and administrator idle-timeout rules remain enabled.

## Registration and sign-in
New accounts use verified Google sign-in to prove email ownership, then enroll Google Authenticator.
There is no institutional-domain restriction. Password registration and old email verification links are disabled.
Authenticator enrollment provides a locally generated QR code and manual setup key, then requires a valid code.
Secrets are encrypted using the existing API_KEY_ENCRYPTION_KEY configuration (or its SECRET_KEY fallback).
Keep that encryption key stable and backed up separately from database backups.
Every sign-in requires an app code or unused recovery code; old remembered-device tokens cannot skip it.
All authentication routes have stopped calling SMTP; SMTP credentials themselves are unchanged.

## Recovery
Ten recovery codes are shown once after enrollment. Store them securely.
Forgot password uses a recovery code to set a password, revoke previous sessions and recovery codes,
and require fresh Authenticator enrollment. Google-only accounts can establish a password this way too.
If both phone and recovery codes are lost, a super administrator can reset Authenticator after independently
verifying the account holder's identity. The action requires a reason and is recorded in the audit history.
It does not reset an administrator's own account or remove bans.

## Archive and backups
Account archival, retained scans/errors, ban protection, and permanent archive history are unchanged.
Database backups are super-admin-only and exclude external image files and server encryption keys.
The existing Git branch-history integration is unchanged.
