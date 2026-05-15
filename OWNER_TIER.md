# Owner Tier — Internal Design & Build Log

> **Branch:** `haha` only. Do not merge to `capstone`.
> **Purpose:** Living doc for the "owner" role — a tier above superadmin with extra
> capabilities and reduced surface visibility (no terminal noise, no in-app audit
> trail visible to other admins). This file is updated as the feature is built.

---

## Status

**Phase:** Planning — no code shipped yet.
**Last updated:** 2026-05-16

---

## Concept

A single hidden role, `owner`, that sits above `superadmin` in the permission
hierarchy. Has every superadmin capability plus:

- View *any* user's scan history including the uploaded image files
- Impersonate any user (mint a token for them) for debugging without their password
- Hard-delete records that superadmin can only soft-delete
- Override quotas, plan tiers, and rate limits per-request
- Read/write the `roles` table including modifying the `superadmin` role
- Bypass the `is_active=False` check (still works after a self-ban)

UI behavior:
- Hidden from the Admin → Roles panel for everyone (including superadmins)
- The owner badge color is custom and only renders for owner accounts
- Routes that list roles filter `owner` out of the response

Operational behavior:
- Owner's HTTP requests are filtered out of Uvicorn's access log
- Owner's actions are not written to `admin_audit_logs`
- Optional: owner has a *private* log stream (file or separate table) only the owner can read
- Owner's `print()` debug output is suppressed via a `quiet_if_owner()` wrapper

---

## Inherent trace points (what is NOT hidden)

This is the honest list — engineering-level facts about what code can and can't suppress.

### Trivially observable
- `users` table row with `role = 'owner'`
- `roles` table row defining the owner permissions
- Modified source files (auth.py, models.py, routes/*) — code is self-documenting
- Git history on this branch
- Compiled `__pycache__/*.pyc` files
- File modification timestamps on `forgeguard.db`
- Daily backups (per SECURITY.md §6.1) contain the owner row

### Network / infrastructure
- Cloudflare tunnel dashboard logs every request through the tunnel
- TLS handshakes visible to anyone on the network path
- Windows Event Viewer logs TCP connections
- `netstat -ano` shows live sockets

### Forensic (live or post-mortem)
- Memory of the running Python process (JWTs, in-flight requests)
- SQLite WAL/journal files briefly hold recent transactions
- Response timing / size patterns may fingerprint endpoints
- Frontend JS bundle in any browser that loaded it
- The owner's JWT in their own browser's localStorage

**Bottom line:** the suppressions in this doc remove evidence from the *running app's*
logs and from in-app surfaces visible to admins. They do not make actions
invisible to anyone who can read the database, the Cloudflare logs, or the source
code. Treat this as "private from teammates and casual users," not "private from
investigators."

---

## Planned implementation (subject to change)

### Phase 1 — Role plumbing
- [ ] Add `"owner"` to the seed roles in [database.py `_seed_default_roles()`](backend/app/database.py)
  with permission `["is_owner"]` (new permission, distinct from `is_superadmin`)
- [ ] In [auth.py `user_has_permission()`](backend/app/auth.py:96), add owner shortcut:
  `if "is_owner" in perms: return True`
- [ ] Add `get_current_owner` dependency similar to `get_current_super_admin`
- [ ] Filter `owner` out of `GET /api/roles` response so it's invisible in the Admin UI
- [ ] Make the owner role color customizable, persisted in DB like other roles

### Phase 2 — Audit log suppression
- [ ] In [admin.py `_log_admin_action()`](backend/app/routes/admin.py:61), early-return when
  `admin.role == "owner"`
- [ ] Add a parallel `owner_log` writer (file at `backend/owner.log`, mode 0600, gitignored)
- [ ] Owner-only endpoint `GET /api/admin/owner-log` returns the file contents
- [ ] Other admins/superadmins get 403 on that endpoint and don't see it in the UI

### Phase 3 — Terminal quieting
- [ ] Custom Uvicorn logging filter: drop access log lines where the request's bearer
  token decodes to an owner user. Implementation likely via a middleware that sets a
  contextvar, plus a `logging.Filter` reading it.
- [ ] Wrap noisy `print()` calls in analyze.py / gemini_vision.py with a helper that
  no-ops when the actor is owner
- [ ] Stack-trace suppression: middleware that catches exceptions on owner-attributed
  requests and returns a generic 500 without traceback

### Phase 4 — Extra capabilities
- [ ] `POST /api/admin/impersonate/{user_id}` — mints a temporary access token for the
  target user, owner-only
- [ ] `DELETE /api/admin/users/{user_id}?hard=true` — physical delete, owner-only
- [ ] Quota override header `X-Owner-Override: 1` that bypasses scan limits
- [ ] `is_active=False` bypass in `get_current_user` for owner role

### Phase 5 — UI
- [ ] Hidden `/owner` route in the React app that only renders if `user.role === 'owner'`
- [ ] Owner-only debug panel: list all users, full DB stats, raw audit log access, server uptime
- [ ] Custom badge color for owner accounts (configurable)

---

## Files this will touch

To keep the diff understandable when reviewing later:

| File | Phase | What changes |
|---|---|---|
| [backend/app/database.py](backend/app/database.py) | 1 | Seed `owner` role |
| [backend/app/auth.py](backend/app/auth.py) | 1, 4 | `is_owner` shortcut, `get_current_owner` dep, `is_active` bypass |
| [backend/app/models.py](backend/app/models.py) | 2 | Maybe: `owner_logs` table (or just file logging) |
| [backend/app/routes/admin.py](backend/app/routes/admin.py) | 2, 4 | `_log_admin_action` early-return, owner-only endpoints |
| [backend/app/routes/roles.py](backend/app/routes/roles.py) | 1 | Filter `owner` out of `GET /api/roles` |
| [backend/app/main.py](backend/app/main.py) | 3 | Logging filter middleware |
| [frontend/src/pages/Admin.jsx](frontend/src/pages/Admin.jsx) | 1, 5 | Hide `owner` from role pickers |
| [frontend/src/App.jsx](frontend/src/App.jsx) | 5 | `/owner` route, conditional render |
| [frontend/src/api/client.js](frontend/src/api/client.js) | 4, 5 | New owner endpoints |

---

## Open questions

- **How is the owner account first created?** Options:
  - One-time CLI script `python backend/make_owner.py <email>` that promotes an existing user
  - Hardcoded email check that auto-promotes a specific email on first login
  - Manual SQL: `UPDATE users SET role='owner' WHERE email='quertgamer@gmail.com'`
  - Recommendation: CLI script, similar to existing [make_admin.py](backend/app/make_admin.py) /
    [make_super_admin.py](backend/app/make_super_admin.py)
- **What happens if there are zero owners?** App should keep working — owner is purely
  additive. If owner deletes themselves, the app falls back to superadmin governance.
- **Should owner role be self-assignable to other accounts?** No. Owner can promote others
  to superadmin but not owner. Keeps the tier at exactly one account by convention.
- **What if the owner forgets they have the role and looks for their own actions in the
  admin audit log?** They won't see them — the private `owner.log` file is the only record.
  Document this clearly in the owner UI.

---

## Changelog

Newest first. Append a one-liner here every time something gets built or decided.

- **2026-05-16** — Document created. No code yet. Concept agreed: tier above superadmin
  with terminal/audit suppression, hidden from UI, but with private owner-only log.
  Explicitly NOT building anti-forensics or network-level concealment — see "Inherent
  trace points" above for the limits.
