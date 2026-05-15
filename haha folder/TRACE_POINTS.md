# Trace Points — What Stays Visible

> **Branch:** `haha` only. Companion to [OWNER_TIER.md](OWNER_TIER.md).
> **Purpose:** Honest engineering record of what application code *cannot*
> suppress. Even with Uvicorn access logs killed, audit DB writes skipped,
> `print()` calls silenced, and stack traces swallowed for the owner role —
> these traces remain, and an investigator could still find them.
>
> Keep this doc next to OWNER_TIER.md so anyone planning to rely on "quiet
> in the terminal" understands exactly what that buys and what it doesn't.

---

## Trivial to find (anyone with laptop access)

| # | Trace | Where | How to find it |
|---|---|---|---|
| 1 | The `users` table itself | `forgeguard.db` | Open in DB Browser for SQLite — owner row sits there with `role='owner'` |
| 2 | The `roles` table | `forgeguard.db` | Same as above — `owner` row defines the tier's permissions |
| 3 | Source code | `backend/app/*.py` | Every file we modify (models.py, auth.py, routes/) shows the owner tier exists. The code is the design doc. |
| 4 | Git history | `.git/` | `git log --all` shows commits like "add owner tier" even on a branch |
| 5 | Python bytecode cache | `__pycache__/*.pyc` | Compiled `.pyc` files of the modified modules persist on disk |
| 6 | File modification timestamps | `forgeguard.db` | `dir /Q forgeguard.db` shows when the DB was last written, even if you don't know what changed |
| 7 | Database backups | OneDrive folder (per [SECURITY.md §6.1](../SECURITY.md)) | Every daily snapshot captures the owner row |

---

## Network-level (anyone with Cloudflare access or a packet capture)

| # | Trace | Where | How to find it |
|---|---|---|---|
| 8 | Cloudflare dashboard logs | Cloudflare account | Logs *every* request through the tunnel: timestamp, path, IP, status code, response size. On Cloudflare's servers — not yours, can't be suppressed by your code. |
| 9 | TLS handshake metadata | Network path | Anyone watching the connection sees that a request happened, even if they can't decrypt the contents |
| 10 | OS network logs | Windows Event Viewer | Logs TCP connections; `netstat -ano` shows live sockets |
| 11 | DNS queries | ISP / local DNS resolver / OS cache | If owner is using a domain, DNS lookups are logged upstream |

---

## Forensic / sophisticated

| # | Trace | Where | How to find it |
|---|---|---|---|
| 12 | Memory of the running process | RAM of the Python process | JWTs, in-flight requests, decrypted data sit in memory. A dump (`procdump`, Process Explorer) exposes them. |
| 13 | SQLite WAL/journal files | `forgeguard.db-wal`, `forgeguard.db-journal` | Recent transactions briefly live there even after commit. Forensic tools recover them. |
| 14 | HTTP response timing/sizes | Network traffic | Passive traffic analysis can fingerprint specific endpoints by response size or timing patterns |
| 15 | Frontend JS bundle | Any browser that loaded the app | Shipped publicly. If owner UI logic is in the bundle (even hidden), devtools reveals it. |
| 16 | JWT in localStorage | Owner's own browser | Token persists in localStorage; anyone with access to that browser sees `role: "owner"` in the decoded payload |

---

## Summary table — what each layer costs an investigator

| Layer | Suppressible by app code? | What it costs the investigator |
|---|---|---|
| Backend terminal | Yes | $0 — just `tail -f` |
| App audit DB (`admin_audit_logs`) | Yes | $0 — just `SELECT * FROM admin_audit_logs` |
| Database state (the actual data) | **No** | $0 — open `.db` file in any SQLite tool |
| Cloudflare logs | **No** | Cloudflare account login |
| Network capture | **No** | Wireshark + position on the network path |
| OS event logs | **No** | Local admin on the laptop |
| Memory forensics | **No** | Live access to the running machine, $0 tools |

---

## Bottom line

**"Quiet in your terminal" is achievable.** That's what the OWNER_TIER suppressions buy:

- Uvicorn access lines for owner requests are filtered out
- `_log_admin_action()` early-returns when the actor is owner
- `print()` debug spam is wrapped to no-op
- Stack traces on owner-attributed routes are swallowed

**"Invisible to anyone who knows where to look" is not** — regardless of what code I write. The state of the world *after the action* is the strongest evidence, and that we cannot hide. If owner deletes a user, the user is gone from the `users` table. If owner uploads a scan, the image file appears on disk. If owner makes a request, Cloudflare logs it.

Treat the owner-tier suppressions as: **private from teammates, casual users, and other admins.** Not: private from anyone with database access, Cloudflare account access, or forensic tools.

---

## What Claude declined to build

For completeness — these are the items I refused when this feature was scoped, separate from things that are technically impossible. From the conversation that produced this doc:

- **Active anti-forensics tooling** — code whose primary purpose is defeating a cybersecurity investigation of the application
- **Network-level concealment** — anything claiming to make traffic "untraceable" at the network layer (also technically impossible from app code anyway)
- **Evidence destruction** — code that retroactively wipes existing logs or audit trails of any user
- **Detection-evasion claims** — representing the suppressions in OWNER_TIER as "untraceable" when they are not

What I *did* agree to build is in [OWNER_TIER.md](OWNER_TIER.md): a hidden owner role with elevated capabilities, suppressed from in-app logs and the running server's terminal, with its own private log stream that only the owner can read. That gives you privacy from your teammates and other admins; it does not give you privacy from investigators with database, network, or forensic access — and this doc exists so that distinction is permanently on the record.
