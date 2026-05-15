# Revelator Security Playbook

> **Purpose of this document**
> This is a self-contained playbook for hardening Revelator's security. It records the
> full system analysis, every recommended change with exact file paths and code, and
> the order to implement them in. If you (or future-Claude) come back to this file
> later, you should be able to pick any item below and implement it without
> re-analyzing the codebase first.
>
> **Last full analysis:** 2026-05-16
> **Stack snapshot at time of writing:** FastAPI backend + React/Vite frontend + SQLite + Cloudflare Tunnel deployment from a school laptop. JWT (HS256) auth, bcrypt passwords, Google OAuth, role-based permissions, Stripe + PayMongo payments (decorative for capstone).

---

## Table of Contents

1. [Threat model](#1-threat-model)
2. [Current security posture](#2-current-security-posture)
3. [Identified gaps (full list)](#3-identified-gaps-full-list)
4. [App-level fixes (priority 1)](#4-app-level-fixes-priority-1)
5. [Cloudflare protections (priority 2)](#5-cloudflare-protections-priority-2)
6. [Operational hardening (priority 3)](#6-operational-hardening-priority-3)
7. [Nice-to-have (priority 4)](#7-nice-to-have-priority-4)
8. [Verification checklist](#8-verification-checklist)
9. [Capstone defense narrative](#9-capstone-defense-narrative)

---

## 1. Threat model

Revelator's realistic threat surface, in rough order of likelihood:

| Threat | Who | Why it matters here |
|---|---|---|
| Bot scraping `/api/auth/register` to create fake accounts | Random internet bots | Cloudflare-exposed endpoint, no captcha, weak password rule |
| Brute force on `/api/auth/login` | Same bots | No rate limit, no lockout |
| Malicious file uploads via `/api/analyze` | Authenticated abuser | No size limit, no MIME check beyond PIL |
| Token leakage via image URLs | Anyone with referer-log access | `?token=...` in image URLs leaks to logs/history |
| API-key theft from DB dump | Anyone who gets the SQLite file | Gemini keys stored plaintext |
| DDoS / traffic flooding | Random | Single laptop with limited bandwidth |
| Cross-site request forgery from another site | Malicious site | `allow_origins=["*"]` lets any origin call the API with the user's cookies/token |
| Forged JWT if `.env` not loaded | Misconfig | `SECRET_KEY` defaults to a public string |
| Database loss | Hardware failure | SQLite on a school laptop, no backups |

What is **out of scope**: nation-state attacks, advanced persistent threats, physical access to the laptop, social engineering. This is a capstone-grade SaaS, not a bank.

---

## 2. Current security posture

### What is already in place (don't re-do these)

- **JWT auth** with separate access (60-min) and refresh (30-day) tokens — [backend/app/auth.py](backend/app/auth.py)
- **bcrypt password hashing** with 72-byte safe truncation — [backend/app/auth.py:21-27](backend/app/auth.py#L21-L27)
- **Google OAuth** via ID-token verification — [backend/app/routes/auth.py:140-205](backend/app/routes/auth.py#L140-L205)
- **Role-based permissions** with a `Role` table — [backend/app/auth.py:83-129](backend/app/auth.py#L83-L129)
- **Admin audit log** (`admin_audit_logs` table) — [backend/app/models.py:116-127](backend/app/models.py#L116-L127)
- **`is_active` enforcement** on every authenticated request — [backend/app/auth.py:78](backend/app/auth.py#L78)
- **Idempotent SQLite migrations** in `_ensure_columns()` — [backend/app/database.py:33](backend/app/database.py#L33)
- **Cloudflare Tunnel** in use for TLS termination — [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)

---

## 3. Identified gaps (full list)

Numbered for reference from later sections.

| # | Gap | File | Severity |
|---|---|---|---|
| G1 | CORS allows all origins | [backend/app/main.py:18](backend/app/main.py#L18) | High |
| G2 | `SECRET_KEY` falls back to a hard-coded default | [backend/app/config.py:24](backend/app/config.py#L24) | High |
| G3 | No file size or MIME validation on `/analyze` | [backend/app/routes/analyze.py:350-376](backend/app/routes/analyze.py#L350-L376) | High |
| G4 | Token passed as query param in image URLs | [frontend/src/api/client.js:174-177](frontend/src/api/client.js#L174-L177) and [analyze.py](backend/app/routes/analyze.py) image route | High |
| G5 | No rate limiting at the app level | Entire app | Medium |
| G6 | API keys stored plaintext in DB | [backend/app/models.py:65](backend/app/models.py#L65) | Medium |
| G7 | Minimum password length is 6 chars | [backend/app/routes/auth.py:86-87](backend/app/routes/auth.py#L86-L87) | Medium |
| G8 | No security HTTP headers (CSP, X-Frame, etc.) | Entire app | Medium |
| G9 | SQLite on a laptop with no backup strategy | Operational | Medium |
| G10 | No request size limit on the FastAPI server | [backend/app/main.py](backend/app/main.py) | Medium |
| G11 | Verbose error messages leak internals | Multiple `HTTPException(detail=str(e))` | Low |
| G12 | `image_path` stored as a string — risk of path traversal if user-controlled | [analyze.py](backend/app/routes/analyze.py) | Low (currently we generate the path ourselves, but worth a guard) |
| G13 | No login lockout after N failures | Entire app | Low |
| G14 | No email verification flow | Auth | Low |

---

## 4. App-level fixes (Priority 1)

**Goal:** Close the bugs that Cloudflare cannot help with. These are the non-negotiables before any panel defense.

> **Estimated total time:** ~45 minutes for all of section 4.

---

### 4.1 Lock down CORS (fixes G1)

**Why:** `allow_origins=["*"]` combined with `allow_credentials=True` is a CORS misconfiguration — modern browsers actually block credentials in this combo, but any same-origin or proxied attacker can still hit the API. Restrict to known frontends only.

**File:** [backend/app/main.py:16-22](backend/app/main.py#L16-L22)

**Change:**
```python
# Before
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# After
from .config import FRONTEND_URL

ALLOWED_ORIGINS = [
    FRONTEND_URL,                    # e.g. http://localhost:5173 or https://revelator.app
    "http://localhost:5173",          # local dev
    "http://localhost:5174",          # vite fallback port
    "https://localhost",              # capacitor android webview
    "capacitor://localhost",          # capacitor ios webview
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
```

**Verify:**
```powershell
# From browser console on a foreign origin (e.g. open https://example.com and run in devtools):
fetch("https://your-tunnel-url/api/health").then(r => r.json())
# Should fail with CORS error
```

---

### 4.2 Fail-fast on default SECRET_KEY (fixes G2)

**Why:** If `.env` fails to load or isn't deployed, the app silently uses `"CHANGE-ME-..."` as the JWT signing key. Anyone reading the source code can then forge tokens.

**File:** [backend/app/config.py:24](backend/app/config.py#L24)

**Change:**
```python
# Replace this line:
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE-ME-generate-a-random-64-char-string")

# With:
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY or SECRET_KEY.startswith("CHANGE-ME"):
    raise RuntimeError(
        "SECRET_KEY is not configured. Generate one with: "
        "python -c \"import secrets; print(secrets.token_hex(32))\" "
        "and put it in C:\\Revelator\\.env"
    )
```

**Verify:**
```powershell
# With SECRET_KEY missing from .env, the server should refuse to start.
cd C:\Revelator\backend
python run.py
# Should print RuntimeError and exit.
```

---

### 4.3 Validate uploads on `/analyze` (fixes G3, G10)

**Why:** A 500MB PNG bomb would OOM the laptop. A `.exe` renamed `.png` would crash PIL with a stack trace exposing internals.

**File:** [backend/app/routes/analyze.py](backend/app/routes/analyze.py) around line 350

**Change — add at module top:**
```python
MAX_UPLOAD_BYTES = 15 * 1024 * 1024   # 15 MB ceiling for a document image
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
```

**Inside `analyze_document()`, before `image_data = imageFile.file.read()`:**
```python
# Content-Type allowlist
if imageFile.content_type and imageFile.content_type not in ALLOWED_CONTENT_TYPES:
    raise HTTPException(status_code=415, detail="Unsupported image format")

# Size guard — read in a bounded way
image_data = imageFile.file.read(MAX_UPLOAD_BYTES + 1)
if len(image_data) > MAX_UPLOAD_BYTES:
    raise HTTPException(status_code=413, detail="Image too large (max 15 MB)")

# Magic-byte check via PIL (already happening in try/except — keep it)
try:
    image = Image.open(io.BytesIO(image_data))
    image.verify()                              # PIL header sanity
    image = Image.open(io.BytesIO(image_data))  # reopen after verify (verify closes)
    if image.mode != "RGB":
        image = image.convert("RGB")
    original_width, original_height = image.size
except Exception:
    raise HTTPException(status_code=400, detail="Invalid or corrupted image")
```

**Verify:**
```powershell
# Try uploading a non-image file:
curl -X POST -H "Authorization: Bearer <token>" -F "imageFile=@notes.txt" http://localhost:8000/api/analyze
# Should return 415 or 400, NOT 500.
```

---

### 4.4 Stop leaking tokens in image URLs (fixes G4)

**Why:** Image URLs look like:
```
/api/history/abc123/image?token=eyJ...
```
That token is logged in server access logs, browser history, and any HTTP referer headers. If you ever proxy through a CDN, the CDN sees it too.

**Two viable approaches:**

**Option A — Short-lived signed URLs (recommended, ~30 min):**
1. Add a `signed_image_token(scan_id, exp_seconds=300)` helper that JWT-encodes only `{scan_id, exp}`, *not* the user JWT.
2. Image route validates this scan-scoped token instead of the auth token.
3. Frontend calls a new `getScanImageSignedUrl(scanId)` endpoint that returns the signed URL on demand.

**Option B — Fetch-as-blob (simpler, ~10 min):**
Frontend fetches image binary with `Authorization` header, converts to a blob URL:
```js
// frontend/src/api/client.js
async getScanImageBlob(scanId) {
  const res = await fetch(`${API_BASE}/history/${scanId}/image`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) throw new Error('Failed to load image');
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}
```
Then on each page that shows an image, `useEffect(() => { getScanImageBlob(id).then(setUrl) }, [id])`.

**Recommendation:** Start with Option B — it removes the leak completely with minimal backend work. The route still uses `Depends(get_current_user)` instead of `get_user_from_token`, and `get_user_from_token` can be deleted from [auth.py:132-144](backend/app/auth.py#L132-L144).

---

### 4.5 Strengthen password rule (fixes G7)

**Why:** Six characters is below NIST minimums. Combined with no rate limit, brute force is trivial.

**File:** [backend/app/routes/auth.py:86](backend/app/routes/auth.py#L86)

**Change:**
```python
if len(body.password) < 8:
    raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
if body.password.lower() in {"password", "12345678", "qwerty123", "revelator"}:
    raise HTTPException(status_code=400, detail="Password is too common")
```

**Also update the frontend Register page** to show the new rule so users aren't confused.

---

### 4.6 Sanitize error responses (fixes G11)

**Why:** `HTTPException(detail=str(e))` leaks stack-trace-y info to attackers, e.g., Google OAuth's error includes claim names.

**Find these patterns:**
```python
detail=f"Invalid Google token: {str(e)}"     # auth.py:155
detail=f"Invalid image: {str(e)}"             # analyze.py:376
```

**Replace with generic messages, log the full error server-side:**
```python
import logging
logger = logging.getLogger(__name__)
# ...
except ValueError as e:
    logger.warning(f"Google token rejected: {e}")
    raise HTTPException(status_code=401, detail="Invalid Google token")
```

---

## 5. Cloudflare protections (Priority 2)

**Goal:** Add an edge layer in front of the school laptop so it never sees abusive traffic.

All of these are configured in the **Cloudflare dashboard** (no code changes). Requires a Cloudflare account with the tunnel already running (see [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)).

> **Note:** Quick-tunnel URLs (`*.cfargotunnel.com`) cannot have most security rules attached. To use sections 5.1–5.4 you need either a **named tunnel on a custom domain** (Option B in DEPLOYMENT_GUIDE.md) or a free `*.workers.dev` subdomain bound to the tunnel. Adding a domain is ~$10/year and unlocks every Cloudflare protection.

---

### 5.1 Enable WAF Managed Ruleset

**Where:** Cloudflare dashboard → your domain → **Security → WAF → Managed rules**

**What to enable:**
- Cloudflare Managed Ruleset (free) → set to **Block**
- OWASP Core Ruleset → Sensitivity = Medium, Action = Block

**What this catches:** SQL injection, XSS, command injection, path traversal, known CVE exploits.

**Verify:**
```bash
# Try a classic SQLi probe — should get blocked by Cloudflare, never reaches backend
curl "https://your-domain/api/auth/login?test=1' OR '1'='1"
# Expect: Cloudflare 403 challenge page
```

---

### 5.2 Rate limiting

**Where:** Cloudflare dashboard → **Security → WAF → Rate limiting rules**

**Free tier gives you one rule.** Use it on the highest-value endpoint:

**Rule:** Limit `/api/auth/login`
- **If incoming requests match:** URI Path contains `/api/auth/login`
- **And request method is:** POST
- **Then:** Block requests from the same IP for 1 hour when more than **5 requests in 60 seconds**

**If you upgrade to a paid plan or self-host with Cloudflare Workers, also add:**
- `/api/auth/register` → 3 req/min per IP
- `/api/analyze` → 30 req/min per IP (don't accidentally block legitimate batch use)
- `/api/auth/refresh` → 10 req/min per IP

**Verify:**
```powershell
# Hammer the endpoint
1..10 | ForEach-Object {
  Invoke-WebRequest -Uri https://your-domain/api/auth/login -Method POST -Body '{"email":"x@x.com","password":"x"}' -ContentType 'application/json' -SkipHttpErrorCheck
}
# Requests 6-10 should return 429
```

---

### 5.3 Bot Fight Mode

**Where:** **Security → Bots → Configure Super Bot Fight Mode** (free tier)

**Settings:**
- Definitely automated → **Block**
- Likely automated → **Managed Challenge** (CAPTCHA)
- Verified bots → **Allow** (lets Googlebot through)
- **Static resource protection:** ON

**Caveat:** This can occasionally false-positive on legitimate users on shared VPNs. Monitor the **Security Events** dashboard for the first week and whitelist if needed.

---

### 5.4 Security headers (via Transform Rules)

**Where:** **Rules → Transform Rules → Modify Response Header → Create rule**

**Rule name:** `Security headers`
**Set when:** All incoming requests

**Headers to set:**
```
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
Content-Security-Policy: default-src 'self'; img-src 'self' data: blob:; script-src 'self' https://accounts.google.com 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self' https://accounts.google.com https://your-tunnel-url; frame-src https://accounts.google.com
```

**Note:** The `'unsafe-inline'` in script/style is needed because Vite inlines small chunks. After you can verify the production build, tighten with a nonce or hash.

**Verify:**
```powershell
curl -I https://your-domain
# Look for the headers above in the response
```

---

### 5.5 Always Use HTTPS

**Where:** **SSL/TLS → Edge Certificates → Always Use HTTPS** → ON

**Also enable:** Automatic HTTPS Rewrites → ON (rewrites any `http://` link in your HTML to `https://`).

---

### 5.6 Geo-block (optional)

**Where:** **Security → WAF → Custom rules → Create rule**

**Rule name:** `PH-only access` (if you only want Philippine users for the capstone)
**Expression:** `ip.geoip.country ne "PH"`
**Action:** Block

**Skip this if:** You want international demo access (e.g., panel members on VPN, remote reviewers).

---

## 6. Operational hardening (Priority 3)

**Goal:** Survive a hardware failure or compromised database.

---

### 6.1 SQLite backups

**Why:** [backend/forgeguard.db](backend/forgeguard.db) is the single source of truth for users, scans, roles, audit logs. Lose it = lose the app.

**Strategy:** Scheduled task that copies the DB to OneDrive/Google Drive daily.

**Windows Task Scheduler script** (`C:\Revelator\backup_db.ps1`):
```powershell
$src = "C:\Revelator\backend\forgeguard.db"
$stamp = Get-Date -Format "yyyy-MM-dd-HHmm"
$dst = "$env:USERPROFILE\OneDrive\RevelatorBackups\forgeguard-$stamp.db"
New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
Copy-Item -LiteralPath $src -Destination $dst
# Keep last 14 backups, delete older
Get-ChildItem (Split-Path $dst) -Filter "forgeguard-*.db" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -Skip 14 |
  Remove-Item -Force
```

**Schedule:** Task Scheduler → Create Basic Task → Daily at 2:00 AM → Start a Program: `powershell.exe -File C:\Revelator\backup_db.ps1`

**Verify after first run:** Check the OneDrive folder has the timestamped file.

**Better long-term:** Migrate to PostgreSQL on a small managed instance ($5/mo Supabase free tier). Just change `DATABASE_URL` in `.env` — SQLAlchemy abstracts the rest.

---

### 6.2 Encrypt user API keys (fixes G6)

**Why:** If anyone gets the DB file, they have every user's Gemini API key in plaintext. Each key is worth real money on the Google API marketplace.

**Approach:** Symmetric encryption with `cryptography.fernet`. Key lives in `.env`, encrypted blobs live in DB.

**Step 1 — add to `requirements.txt`:**
```
cryptography>=42
```

**Step 2 — add to `.env`:**
```
# Generate once: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
DATA_ENCRYPTION_KEY=...
```

**Step 3 — new file `backend/app/crypto.py`:**
```python
from cryptography.fernet import Fernet
from .config import DATA_ENCRYPTION_KEY

_fernet = Fernet(DATA_ENCRYPTION_KEY.encode())

def encrypt_str(plain: str) -> str:
    if not plain:
        return plain
    return _fernet.encrypt(plain.encode()).decode()

def decrypt_str(cipher: str) -> str:
    if not cipher:
        return cipher
    return _fernet.decrypt(cipher.encode()).decode()
```

**Step 4 — wrap reads/writes in [backend/app/routes/auth.py](backend/app/routes/auth.py):**
```python
# When saving:
key = UserApiKey(api_key=encrypt_str(api_key.strip()), ...)

# When using:
api_key_plain = decrypt_str(active_key_row.api_key)
```

**Step 5 — one-time migration script** (write to `backend/migrate_encrypt_keys.py`):
```python
from app.database import SessionLocal
from app.models import UserApiKey
from app.crypto import encrypt_str

db = SessionLocal()
for k in db.query(UserApiKey).all():
    if k.api_key.startswith("AIza"):  # plaintext check
        k.api_key = encrypt_str(k.api_key)
db.commit()
```

**Run once:** `python backend/migrate_encrypt_keys.py`

**Note:** If `DATA_ENCRYPTION_KEY` is lost, all stored API keys become unrecoverable. Back up the key separately from the DB.

---

### 6.3 Login lockout (fixes G13)

**Why:** Even with Cloudflare rate limiting, a slow distributed brute force (1 attempt/min from 1000 IPs) wouldn't trigger rate limiting but could still succeed on a weak password.

**Schema addition** (add to [backend/app/models.py User class](backend/app/models.py)):
```python
failed_login_count = Column(Integer, default=0)
locked_until = Column(DateTime, nullable=True)
```

**Migration** (add to [backend/app/database.py `_ensure_columns()`](backend/app/database.py)):
```python
if "failed_login_count" not in user_cols:
    conn.execute(text("ALTER TABLE users ADD COLUMN failed_login_count INTEGER DEFAULT 0"))
if "locked_until" not in user_cols:
    conn.execute(text("ALTER TABLE users ADD COLUMN locked_until DATETIME"))
```

**Update `login()`** in [backend/app/routes/auth.py:108](backend/app/routes/auth.py#L108):
```python
@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if user.locked_until and user.locked_until > datetime.utcnow():
        raise HTTPException(status_code=429, detail="Account temporarily locked. Try again later.")

    if not verify_password(body.password, user.hashed_password):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= 5:
            user.locked_until = datetime.utcnow() + timedelta(minutes=15)
            user.failed_login_count = 0
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    user.failed_login_count = 0
    user.locked_until = None
    db.commit()

    return TokenResponse(...)  # existing
```

---

### 6.4 Server-side request size cap (fixes G10)

**Why:** FastAPI/Uvicorn has no built-in request body limit. Even with the per-route check in 4.3, a malicious request to any endpoint could fill memory before reaching the route.

**Two ways:**

**A) Cloudflare (no code) — Free tier caps at 100MB**, paid raises to 500MB. Already done if you're behind CF.

**B) Uvicorn middleware** — `backend/app/main.py`:
```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class BodySizeLimit(BaseHTTPMiddleware):
    MAX_BODY = 20 * 1024 * 1024  # 20 MB

    async def dispatch(self, request, call_next):
        cl = request.headers.get("content-length")
        if cl and int(cl) > self.MAX_BODY:
            return JSONResponse({"detail": "Request too large"}, status_code=413)
        return await call_next(request)

app.add_middleware(BodySizeLimit)
```

---

## 7. Nice-to-have (Priority 4)

Lower-impact polish for after the panel defense.

---

### 7.1 Email verification flow

**Why:** Currently anyone can register with `attacker@victim.com` and the real owner has no idea. Email verification proves they own the inbox.

**Sketch:**
- Add `verification_token` + `verification_token_exp` columns to `users`
- On register, generate a token, email a link to `/verify?token=...`
- Frontend `/verify` page hits `POST /api/auth/verify` with the token, sets `is_verified=True`
- (Optional) Block login until verified

**Requires:** SMTP credentials in `.env` ([config.py:110-114](backend/app/config.py#L110-L114) already has slots).

---

### 7.2 2FA (TOTP) for admin accounts

**Why:** A leaked admin password = full system compromise. TOTP via Google Authenticator is the standard mitigation.

**Library:** `pyotp` + `qrcode`
**Schema:** `totp_secret` column on `User`, plus `totp_enabled` boolean
**Flow:** Settings page → "Enable 2FA" → show QR code → user scans + confirms code → enabled. Login flow asks for 6-digit code after password.

**Apply only to:** `role IN ('admin', 'superadmin')`. Don't force it on regular users — it's friction for free-tier capstone demos.

---

### 7.3 Path-traversal guard on `image_path`

**Why:** Currently safe because we generate the filename ourselves with `secrets.token_hex()`, but a future code change could break this assumption. One-line defense.

**File:** [backend/app/routes/analyze.py](backend/app/routes/analyze.py) wherever the image is saved/served.

**Add:**
```python
from pathlib import Path

def safe_upload_path(filename: str) -> Path:
    full = (UPLOAD_DIR / filename).resolve()
    if not str(full).startswith(str(UPLOAD_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")
    return full
```

Use everywhere a scan's `image_path` is resolved to disk.

---

### 7.4 Audit log retention + UI

**Why:** [admin_audit_logs](backend/app/models.py#L116) grows forever. After 6 months you'll have thousands of rows and the admin UI will lag.

**Add:** A daily cron (same Task Scheduler approach as 6.1) that runs:
```sql
DELETE FROM admin_audit_logs WHERE created_at < datetime('now', '-90 days');
```

**Plus:** A "Download CSV" button in the Admin panel for audit exports before pruning.

---

### 7.5 Security.txt

**Why:** Standard place for security researchers to report vulnerabilities. Costs nothing.

**Create:** `frontend/public/.well-known/security.txt`
```
Contact: mailto:security@your-domain
Expires: 2027-01-01T00:00:00.000Z
Preferred-Languages: en, tl
Canonical: https://your-domain/.well-known/security.txt
```

---

## 8. Verification checklist

After implementing any priority block, walk through this list:

### Priority 1 (App-level)
- [ ] Foreign origin can't call `/api/health` (CORS blocked)
- [ ] Server refuses to start without `SECRET_KEY` in `.env`
- [ ] Uploading a `.txt` file to `/analyze` returns 415, not 500
- [ ] Uploading a 20MB image to `/analyze` returns 413
- [ ] Image URLs no longer contain `?token=...` (check Network tab)
- [ ] Registering with password `"abc"` is rejected
- [ ] Login error response doesn't leak DB internals

### Priority 2 (Cloudflare)
- [ ] WAF blocks `?test=1' OR '1'='1`
- [ ] 6th login attempt in 60 seconds returns 429
- [ ] `curl -I https://your-domain` shows security headers
- [ ] Visiting `http://your-domain` redirects to `https://`

### Priority 3 (Operational)
- [ ] OneDrive folder has today's `forgeguard-YYYY-MM-DD-HHMM.db`
- [ ] `SELECT api_key FROM user_api_keys` shows base64-looking ciphertext, not `AIza...`
- [ ] 5 wrong logins → 6th returns "Account temporarily locked"

---

## 9. Capstone defense narrative

When a panel asks "how is the system secured?", the elevator pitch is:

> "Revelator uses a layered defense model. At the edge, Cloudflare provides DDoS
> mitigation, a managed Web Application Firewall covering OWASP Top 10, rate
> limiting on authentication endpoints, and bot challenge for automated abuse.
> At the application layer, we use JWT-based authentication with bcrypt password
> hashing, role-based access control with a custom permission system, and an
> append-only audit log for all administrative actions. User-supplied API keys
> are encrypted at rest with Fernet symmetric encryption. File uploads are
> validated by content type and size before processing. Login attempts are
> rate-limited and accounts lock after repeated failures."

Each clause maps to a section above. If a panelist drills into any one, you have
the file and line number to point at.

---

## Implementation order (recommended)

If you're picking this up cold:

1. **Section 4.1 (CORS)** — 5 min, immediate win
2. **Section 4.2 (SECRET_KEY)** — 5 min, prevents misconfig disasters
3. **Section 4.3 (Upload validation)** — 15 min, closes the easy DoS vector
4. **Section 4.4 (Token in URLs — Option B)** — 15 min, removes leaked-token risk
5. **Section 4.5–4.6 (Passwords + errors)** — 10 min
6. **Commit, deploy, sanity-check** — verify nothing broke
7. **Section 5.1–5.5 (Cloudflare dashboard work)** — 30 min, no code
8. **Section 6.1 (Backups)** — 15 min, set-and-forget
9. **Section 6.2 (API key encryption)** — 30 min if you have time
10. **Section 6.3–6.4** — when convenient
11. **Section 7** — post-defense polish

Total time for sections 4-6: **~2.5 hours** of focused work, spread over a couple of sessions.
