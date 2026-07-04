# Hosting Revelator (completely free)

Run the whole app on one laptop (the "host" / server, operated by the super admin)
and reach it from anywhere via a free Cloudflare Tunnel. Everything here is free.
Where a free option has a catch, it says so.

## The free stack
- **Public URL:** Cloudflare **quick tunnel** (free, no account). Catch: the URL is
  random and **changes each time the tunnel restarts**. A permanent URL needs a
  domain; the only free domain is `.eu.org` (free, approval takes days). See "Stable URL".
- **One tunnel = whole app:** the backend serves the built frontend, so a single
  tunnel exposes everything at one URL.
- **Database:** local SQLite file (free). Optional free shared cloud DB via Turso (below).
- **2FA:** TOTP / Google Authenticator (free).

## One-time setup
1. Install **cloudflared** (free):
   `winget install --id Cloudflare.cloudflared`
   (or download from Cloudflare's site).
2. Install backend deps:
   `venv\Scripts\pip install -r backend\requirements.txt`
3. Build the frontend once, with a same-origin API base (PowerShell):
   ```powershell
   cd frontend
   npm install
   $env:VITE_API_URL=""      # so the app calls /api on the same host
   npm run build             # produces frontend/dist (served by the backend)
   ```

## Run (each time you host)
From the project root, run **host.bat**. It opens two windows:
- **Revelator Server** - backend + built frontend at http://localhost:8000
- **Cloudflare Tunnel** - prints your public https URL (e.g.
  `https://random-words.trycloudflare.com`). Share that URL.

Close both windows to stop hosting.

## Shared database (free, optional) - so every host sees the same data
By default the DB is `backend/forgeguard.db` and travels with the host laptop.
For a truly shared DB (no data moves on handoff), use Turso's free tier (no card):
1. Create a free DB at turso.tech.
2. Put its libSQL URL + token in `backend/.env`:
   `DATABASE_URL=sqlite+libsql://<db>.turso.io?authToken=<token>`
   (needs the `sqlalchemy-libsql` driver; ask and I'll wire it in).
Every host then connects to the same cloud DB.

## Stable URL (free, optional)
Quick-tunnel URLs change on restart. For a permanent URL, for free:
- Register a free `.eu.org` domain (approval can take days), add it to Cloudflare
  (free plan), then switch to a **named** tunnel (stable hostname). Ask for the
  exact commands when you have the domain.
- If a few dollars is ever OK, any cheap domain works instantly with a named tunnel.

## Handing off the host (super admin -> another laptop)
Planned via the **Host Control** panel: the new host runs `host.bat`, opens the
super admin panel, and clicks **Claim host**. With the shared Turso DB, no data
moves. Until that panel ships, hand off by copying `backend/forgeguard.db` and
`backend/uploads/` to the new host.

## Status of the free-hosting pieces
- [x] Single-origin serving (backend serves the built frontend)
- [x] `host.bat` one-command launcher + free quick tunnel
- [ ] Host Control panel (super admin claims host, shows current public URL)
- [ ] 2FA (TOTP / Google Authenticator)
- [ ] Turso shared-DB driver wiring
