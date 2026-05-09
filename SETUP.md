# Revelator Setup Guide

For your groupmates to get Revelator running locally.

## System Requirements

- **Node.js** 18+ — https://nodejs.org
- **Python** 3.9+ — https://www.python.org
- **Android Studio** (for APK builds) — https://developer.android.com/studio
- **Git** — for cloning the repo

---

## Quick Start (5 min)

### 1. Clone & Install

```bash
git clone https://github.com/VillAlfonso/forgeguard-v2.git
cd forgeguard-v2
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate it (Windows)
venv\Scripts\activate.bat

# Or on PowerShell:
# venv\Scripts\Activate.ps1

```

✅ You should see `(venv)` at the start of your prompt after activation.

Create file `backend/.env` with your API keys:
```
GEMINI_API_KEY=<ask team lead>
STRIPE_SECRET_KEY=<ask team lead>
PAYMONGO_SECRET_KEY=<ask team lead>
GOOGLE_CLIENT_ID=<ask team lead>
GOOGLE_CLIENT_SECRET=<ask team lead>
```

Then install dependencies and run:
```bash
pip install -r requirements.txt
python run.py
```

Backend starts at http://localhost:8000

### 3. Frontend Setup

In a **new terminal**:

```bash
cd frontend
npm install
npm run dev
```

App opens at http://localhost:5173

---

## Environment Variables

### Backend (`backend/.env`)
Copy from `C:\Revelator\.env` or use the keys in `API_KEYS.md`

### Frontend (`frontend/.env`)
```
VITE_API_URL=http://localhost:8000
VITE_GOOGLE_CLIENT_ID=<ask team lead>
```

---

## Building Android APK

Prerequisites: Android Studio installed, ANDROID_HOME set

```bash
cd frontend

# 1. Build web assets
npm run build

# 2. Sync to Android
npx cap sync android

# 3. Build APK (takes 2-5 min)
cd android
.\gradlew.bat assembleDebug

# APK is at: app\build\outputs\apk\debug\app-debug.apk
```

Transfer to phone, install, and test.

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `(venv)` doesn't appear after activation | Try `venv\Scripts\Activate.ps1` instead of `.bat`; or use Command Prompt instead of PowerShell |
| `venv\Scripts\activate` not found | Run `python -m venv venv` again in the `backend/` folder |
| Python not found | Install Python from https://www.python.org (add to PATH during install) |
| `pip install` fails | Try `python -m pip install -r requirements.txt` instead |
| `npm install` fails | Delete `node_modules/` and `package-lock.json`, run again |
| Backend won't start | Check port 8000 isn't in use; ensure `.env` has API keys |
| Frontend can't connect to backend | Edit `frontend/.env` → `VITE_API_URL=http://YOUR_PC_IP:8000` |
| APK build fails | Ensure Android SDK path is set in `android/local.properties` |
| Google Sign-In fails on Android | Need `google-services.json` in `frontend/android/app/` (contact team lead) |

---

## Project Structure

```
forgeguard-v2/
├── backend/               # FastAPI + SQLite
│   ├── app/
│   │   ├── models.py     # Database models
│   │   ├── routes/       # API endpoints
│   │   └── forgery/      # Gemini Vision integration
│   └── run.py
├── frontend/             # React + Vite
│   ├── src/
│   │   ├── pages/        # Login, Register, Scan, Account
│   │   ├── components/
│   │   └── App.jsx
│   ├── android/          # Capacitor Android project
│   └── capacitor.config.ts
├── docs/                 # Architecture, deployment guides
└── API_KEYS.md          # ⚠️ Credentials (in .gitignore)
```

---

## Key Features

- ✅ Document forensics with Gemini Vision AI
- ✅ Email/password auth + Google OAuth
- ✅ Payment with Stripe & PayMongo
- ✅ Mobile app (Android APK via Capacitor)
- ✅ Scan history & admin dashboard

---

## Development Workflow

1. **Backend changes** → Run `python run.py` (auto-reloads)
2. **Frontend changes** → Auto-reload at http://localhost:5173
3. **Android changes** → `npm run build && npx cap sync android && cd android && .\gradlew.bat assembleDebug`

---

## Questions?

- Check `docs/` folder for architecture & API details
- Backend API docs at http://localhost:8000/docs (when running)
- Ask your team lead for API keys / credentials

Good luck! 🚀
