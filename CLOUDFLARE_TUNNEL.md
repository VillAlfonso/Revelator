# How the public URL / Cloudflare tunnel works (no account needed)

You asked how there's a public URL when you don't even have a Cloudflare account.
Answer: I used a Cloudflare **quick tunnel**, which needs no account, no login, and no
domain. Here is exactly what happened and how to reproduce it.

## What a quick tunnel is
`cloudflared` (Cloudflare's tunnel client) dials OUT from your laptop to Cloudflare's
edge and Cloudflare hands back a random public https URL
(e.g. `https://bowl-inside-alike-staff.trycloudflare.com`). Traffic to that URL is
routed back down the tunnel to a local port on your laptop. No inbound ports, no router
config, no account. Your laptop stays behind NAT - there is no public IP, just this URL.

## Exactly what I did
1. Downloaded the cloudflared binary (a single .exe, no install):
   `curl -L -o tools/cloudflared.exe https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe`
2. Ran the Revelator server on a local port. I used **8010** because your `:8000` was
   already taken by a different app ("AAAFlow Studio").
3. Opened the tunnel to it: `tools/cloudflared.exe tunnel --url http://localhost:8010`
   cloudflared printed the public URL. It stays up while that process runs.

## Reproduce it (or just run host.bat)
```
cd frontend
$env:VITE_API_URL=""      # build the UI to call the API on the same host
npm run build
cd ..\backend
python run.py             # serves the app on :8000
# in another terminal:
..\tools\cloudflared.exe tunnel --url http://localhost:8000
```
`host.bat` does the server + tunnel in one step.

## Caveats
- The URL is **random and changes every restart**. Account-less tunnels have no stable name.
- No uptime guarantee (Cloudflare's terms).
- It is publicly reachable while up. Registration is open; don't post the link publicly.

## The red "Dangerous" warning, and how to remove it
That warning is **Google Safe Browsing**, not your app. Random `*.trycloudflare.com`
hostnames get flagged because phishers abuse them. You cannot whitelist a trycloudflare
URL. The only real fix is to stop using the shared `trycloudflare.com` domain and use
**your own domain with a named tunnel**:
1. Free Cloudflare account, add a domain to it. (A domain is the one thing that is not
   free - unless you use a slow-to-approve free `.eu.org`.)
2. `cloudflared login`  (authorizes cloudflared to your account/domain, opens a browser)
3. `cloudflared tunnel create revelator`
4. `cloudflared tunnel route dns revelator app.yourdomain.com`
5. `cloudflared tunnel run revelator`
Now the app is at `https://app.yourdomain.com` - stable, and not flagged as dangerous.
Until you have a domain, the trycloudflare URL works but shows the warning (users can
click Details -> "visit this unsafe site"), which is fine for testing but not client-ready.
