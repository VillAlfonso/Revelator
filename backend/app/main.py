"""
Revelator SaaS API
==================
Forensic document forgery detection - FastAPI gateway + Gemini Vision.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import APP_NAME, APP_VERSION, FRONTEND_URL, UPLOAD_DIR
from .database import init_db
from .routes import auth, analyze, payments, admin, roles, rooms, prompt_analytics

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
app.include_router(prompt_analytics.router)


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


# ── Android app download ──────────────────────────────────────────────────
# The built debug APK is staged at backend/downloads/revelator.apk and served
# here so the site can offer it directly. Registered before the SPA catch-all
# below so this exact path wins. Rebuild the APK with:
#   cd frontend && (build web with VITE_API_URL=https://revelator.site)
#   npx cap sync android && android/gradlew assembleDebug
#   cp android/app/build/outputs/apk/debug/app-debug.apk backend/downloads/revelator.apk
_APK_PATH = Path(__file__).resolve().parent.parent / "downloads" / "revelator.apk"


@app.get("/download/revelator.apk")
def download_apk():
    if not _APK_PATH.is_file():
        raise HTTPException(status_code=404, detail="APK not available")
    return FileResponse(
        str(_APK_PATH),
        media_type="application/vnd.android.package-archive",
        filename="revelator.apk",
    )


# ── Single-origin hosting: serve the built frontend ───────────────────────
# After `npm run build`, frontend/dist exists and the backend serves the whole
# app, so ONE Cloudflare Tunnel exposes everything at a single URL. In dev
# (no dist) this block is skipped and you use the Vite dev server as before.
_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    _assets = _DIST / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        # /api/* routes are registered above and take precedence; guard anyway.
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (_DIST / full_path).resolve()
        if str(candidate).startswith(str(_DIST)) and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_DIST / "index.html"))
