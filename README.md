# Revelator v2

Forensic document analysis SaaS — minimal-backend rewrite.

## Stack

| Layer        | Tech                                     |
|--------------|------------------------------------------|
| Web frontend | React + Vite + Firebase SDK              |
| Mobile       | React Native (later)                     |
| Auth         | Firebase Authentication (email + Google) |
| Database     | Cloud Firestore                          |
| File storage | Firebase Storage                         |
| Backend API  | FastAPI on Oracle Cloud                  |
| AI (live)    | Google Gemini Vision                     |
| AI (later)   | Fine-tuned LLaVA on Hugging Face Spaces  |
| Payments     | Stripe + PayMongo (web) / SDK (mobile)   |

## Layout

```
v2/
├── backend/   FastAPI service (analyze + payments + Firebase Admin)
├── web/       React + Firebase web app
└── mobile/    React Native (deferred — see phase 2)
```

## Why a rewrite

The Legacy/ build owned its own user table, password hashing, JWT issuing,
and Google OAuth verification. With Firebase handling auth + DB directly
from the client, the backend collapses to two responsibilities:

  1. Run the AI pipeline (Gemini, LLaVA) on uploaded images.
  2. Process payment webhooks from Stripe and PayMongo.

Everything else — sign in, sign up, password reset, profile edits, scan
history reads, plan reads — happens on the client through the Firebase SDK.

## Setup order

1. Create a Firebase project (Auth + Firestore + Storage). See
   [docs/FIREBASE_SETUP.md](docs/FIREBASE_SETUP.md).
2. Configure `backend/.env` from `.env.example`.
3. Configure `web/.env` from `.env.example`.
4. `cd backend && pip install -r requirements.txt && python run.py`
5. `cd web && npm install && npm run dev`

## Deployment

| Component | Target          | Notes                            |
|-----------|-----------------|----------------------------------|
| backend   | Oracle Free VM  | Docker or systemd + uvicorn      |
| web       | Vercel / GitHub | Static `npm run build` output    |
| LLaVA     | HF Spaces       | When fine-tuned weights ready    |

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).
