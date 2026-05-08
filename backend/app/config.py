"""Revelator v2 backend configuration. All settings come from environment variables."""

import os
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(ENV_PATH)

# ── Firebase Admin ──────────────────────────────────────────────────
FIREBASE_CREDENTIALS_FILE = os.getenv("FIREBASE_CREDENTIALS_FILE", "./firebase-service-account.json")
FIREBASE_STORAGE_BUCKET = os.getenv("FIREBASE_STORAGE_BUCKET", "")

# ── App ─────────────────────────────────────────────────────────────
APP_NAME = os.getenv("APP_NAME", "Revelator")
APP_VERSION = os.getenv("APP_VERSION", "2.0.0")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# ── Plan limits / pricing ───────────────────────────────────────────
UNLIMITED = -1
FREE_SCANS_PER_MONTH = int(os.getenv("FREE_SCANS_PER_MONTH", "10"))
PRO_SCANS_PER_MONTH = int(os.getenv("PRO_SCANS_PER_MONTH", "-1"))
PREMIUM_SCANS_PER_MONTH = int(os.getenv("PREMIUM_SCANS_PER_MONTH", "-1"))
PRO_PRICE_USD = float(os.getenv("PRO_PRICE_USD", "5"))
PREMIUM_PRICE_USD = float(os.getenv("PREMIUM_PRICE_USD", "10"))

PLAN_LIMITS = {
    "free": FREE_SCANS_PER_MONTH,
    "pro": PRO_SCANS_PER_MONTH,
    "premium": PREMIUM_SCANS_PER_MONTH,
}

# Plans that include the AI/LLM explanation
LLM_PLANS = {"premium"}

# ── Gemini Vision ───────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_VISION_MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-flash-lite")

# ── LLaVA on Hugging Face ───────────────────────────────────────────
LLAVA_DETECTIVE_URL = os.getenv("LLAVA_DETECTIVE_URL", "")
LLAVA_SHERLOCK_URL = os.getenv("LLAVA_SHERLOCK_URL", "")
LLAVA_API_KEY = os.getenv("LLAVA_API_KEY", "")

# ── LLM explanation (Groq / Ollama) ─────────────────────────────────
USE_CLOUD_LLM = os.getenv("USE_CLOUD_LLM", "true").lower() == "true"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

# ── Payments — Stripe ───────────────────────────────────────────────
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID_PRO = os.getenv("STRIPE_PRICE_ID_PRO", "")
STRIPE_PRICE_ID_PREMIUM = os.getenv("STRIPE_PRICE_ID_PREMIUM", "")

# ── Payments — PayMongo ─────────────────────────────────────────────
PAYMONGO_SECRET_KEY = os.getenv("PAYMONGO_SECRET_KEY", "")
PAYMONGO_PUBLIC_KEY = os.getenv("PAYMONGO_PUBLIC_KEY", "")
PAYMONGO_WEBHOOK_SECRET = os.getenv("PAYMONGO_WEBHOOK_SECRET", "")
