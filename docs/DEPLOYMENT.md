# Deployment Guide

This is the cheap-but-real production setup for Revelator v2.

| Component  | Where                  | Cost           |
|------------|------------------------|----------------|
| Web app    | Vercel (or GitHub Pages) | Free          |
| Backend    | Oracle Cloud Free VM   | Free (forever) |
| Database   | Firebase Firestore     | Free tier      |
| Auth       | Firebase Auth          | Free tier      |
| Storage    | Firebase Storage       | Free 5 GB      |
| AI         | Gemini Vision API      | Free tier (rate-limited), or pay-as-you-go |
| LLaVA tier | Hugging Face Spaces    | Free CPU / paid GPU |

## 1. Deploy the backend (Oracle Cloud)

### 1a. Provision a free VM

1. Sign up at https://cloud.oracle.com → enable Always Free.
2. Create an **Ampere A1 Compute** instance (4 OCPU, 24 GB RAM) — the most generous free tier.
   - OS: **Ubuntu 22.04**
   - Add an SSH key.
   - Open ports 80, 443, 8000 in the network security group.
3. SSH in. Install the basics:
   ```bash
   sudo apt update && sudo apt install -y python3-pip python3-venv git nginx
   ```

### 1b. Pull and run

```bash
git clone <your repo> revelator
cd revelator/v2/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Upload your firebase-service-account.json here (do NOT commit it).
scp firebase-service-account.json oracle:/home/ubuntu/revelator/v2/backend/

cp .env.example .env
nano .env   # fill in keys
```

### 1c. systemd service

Create `/etc/systemd/system/revelator.service`:

```ini
[Unit]
Description=Revelator backend
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/revelator/v2/backend
ExecStart=/home/ubuntu/revelator/v2/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now revelator
sudo systemctl status revelator
```

### 1d. nginx + HTTPS

```nginx
# /etc/nginx/sites-available/revelator
server {
    listen 80;
    server_name api.yourdomain.com;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        client_max_body_size 25M;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/revelator /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d api.yourdomain.com
```

## 2. Deploy the web app (Vercel)

```bash
cd v2/web
npm install -g vercel
vercel
```

Set the env vars in the Vercel dashboard (Project → Settings → Environment Variables):

```
VITE_API_URL=https://api.yourdomain.com
VITE_FIREBASE_API_KEY=…
VITE_FIREBASE_AUTH_DOMAIN=…
VITE_FIREBASE_PROJECT_ID=…
VITE_FIREBASE_STORAGE_BUCKET=…
VITE_FIREBASE_MESSAGING_SENDER_ID=…
VITE_FIREBASE_APP_ID=…
```

After deploying, add the Vercel domain (e.g. `revelator.vercel.app`) to Firebase **Authentication → Settings → Authorized domains**.

Cheaper alternative: **GitHub Pages** with the `vite-plugin-static-copy` setup, or **Cloudflare Pages**. Both free.

## 3. Wire up Stripe

1. https://dashboard.stripe.com → create two **Products** (Pro $5/mo, Premium $10/mo) → copy the price IDs.
2. **Developers → API keys** → copy live keys.
3. **Developers → Webhooks → Add endpoint**:
   - URL: `https://api.yourdomain.com/api/payments/stripe-webhook`
   - Events: `checkout.session.completed`, `customer.subscription.deleted`, `customer.subscription.paused`
   - Copy the signing secret.
4. Update `backend/.env` with `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID_PRO`, `STRIPE_PRICE_ID_PREMIUM`.
5. Restart the backend: `sudo systemctl restart revelator`.

## 4. Wire up PayMongo (Philippines)

1. https://dashboard.paymongo.com → API keys → copy public + secret keys.
2. **Webhooks → Add endpoint**:
   - URL: `https://api.yourdomain.com/api/payments/paymongo-webhook`
   - Event: `checkout_session.payment.paid`
   - Copy the secret.
3. Update `backend/.env` with `PAYMONGO_SECRET_KEY`, `PAYMONGO_PUBLIC_KEY`, `PAYMONGO_WEBHOOK_SECRET`.

## 5. (Later) Deploy LLaVA on Hugging Face Spaces

When the fine-tuned weights are ready:

1. Create two Spaces: `<you>/revelator-llava-detective` and `<you>/revelator-llava-sherlock`.
2. Use the Gradio template; expose `/api/predict` returning the JSON shape documented in `backend/app/forgery/llava_client.py`.
3. Set `LLAVA_DETECTIVE_URL` and `LLAVA_SHERLOCK_URL` in `backend/.env`.
4. Restart. The Detective/Sherlock tiers automatically wake up — no code change needed.

## 6. Smoke test

After deploying:

```
GET https://api.yourdomain.com/                      → {"name":"Revelator"…}
GET https://api.yourdomain.com/api/health            → {"status":"ok"}
GET https://api.yourdomain.com/api/document-types    → {"document_types":[…]}
```

Open the web app, sign up, run a scan, watch the result populate. Check Firestore → `scans` collection, your scan should appear.

## 7. Monitoring

- **Backend**: `sudo journalctl -u revelator -f` for live logs
- **Firebase usage**: Console → Usage and billing
- **Gemini quota**: https://ai.dev/rate-limit (free tier) or AI Studio billing
- **Stripe events**: Dashboard → Events
- **PayMongo events**: Dashboard → Webhooks → recent deliveries
