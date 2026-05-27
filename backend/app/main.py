"""
Revelator SaaS API
==================
Forensic document forgery detection - FastAPI gateway + Gemini Vision.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import APP_NAME, APP_VERSION, FRONTEND_URL, UPLOAD_DIR
from .database import init_db
from .routes import auth, analyze, payments, admin, roles, rooms

app = FastAPI(title=f"{APP_NAME} API", description="AI-powered document forgery detection SaaS", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(analyze.router)
app.include_router(payments.router)
app.include_router(admin.router)
app.include_router(roles.router)
app.include_router(rooms.router)


@app.on_event("startup")
async def startup_event():
    print("\n" + "=" * 50)
    print(f"{APP_NAME} API v{APP_VERSION} Starting...")
    print("=" * 50)
    init_db()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  Upload directory: {UPLOAD_DIR}")
    print("=" * 50 + "\n")


@app.get("/api/health")
def health_check():
    return {"status": "healthy", "version": APP_VERSION}
