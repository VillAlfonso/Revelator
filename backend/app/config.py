"""
ForgeGuard Configuration
========================
All settings loaded from environment variables.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
ENV_PATH = Path(__file__).parent.parent.parent / ".env"
load_dotenv(ENV_PATH)


# ============================================
# DATABASE
# ============================================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./forgeguard.db")

# ============================================
# AUTH / JWT
# ============================================
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE-ME-generate-a-random-64-char-string")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

# ============================================
# PAYMENTS (Stripe)
# ============================================
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID_BASIC = os.getenv("STRIPE_PRICE_ID_BASIC", "")
STRIPE_PRICE_ID_PRO = os.getenv("STRIPE_PRICE_ID_PRO", "")

# ============================================
# LLM
# ============================================
USE_CLOUD_LLM = os.getenv("USE_CLOUD_LLM", "false").lower() == "true"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

# ============================================
# YOLO
# ============================================
YOLO_WEIGHTS_PATH = os.getenv("YOLO_WEIGHTS_PATH", "./weights/best.pt")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.25"))

# ============================================
# APP
# ============================================
APP_NAME = "ForgeGuard"
APP_VERSION = "2.0.0"
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
API_URL = os.getenv("API_URL", "http://localhost:8000")

# Free tier limits
FREE_SCANS_PER_MONTH = int(os.getenv("FREE_SCANS_PER_MONTH", "10"))
BASIC_SCANS_PER_MONTH = int(os.getenv("BASIC_SCANS_PER_MONTH", "100"))
PRO_SCANS_PER_MONTH = int(os.getenv("PRO_SCANS_PER_MONTH", "1000"))

# ============================================
# EMAIL (optional, for password reset etc.)
# ============================================
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@forgeguard.app")
