"""
Revelator SaaS API
==================
Forensic document forgery detection - FastAPI gateway + Gemini Vision.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import ALLOWED_ORIGINS, APP_NAME, APP_VERSION, UPLOAD_DIR
from .database import init_db
from .routes import auth, analyze, payments, admin, prompt_analytics

app = FastAPI(title=f"{APP_NAME} API", description="AI-powered document forgery detection SaaS", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """Reject cross-site browser mutations and attach baseline security headers."""
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        fetch_site = request.headers.get("sec-fetch-site")

        if origin and origin.rstrip("/") not in ALLOWED_ORIGINS:
            return JSONResponse(status_code=403, content={"detail": "Cross-site request blocked"})
        if referer and not any(referer.startswith(f"{allowed}/") for allowed in ALLOWED_ORIGINS):
            return JSONResponse(status_code=403, content={"detail": "Cross-site request blocked"})
        if fetch_site == "cross-site":
            return JSONResponse(status_code=403, content={"detail": "Cross-site request blocked"})

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://accounts.google.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' https://accounts.google.com https://generativelanguage.googleapis.com; "
        "frame-src 'self' https://accounts.google.com; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )
    return response

app.include_router(auth.router)
app.include_router(analyze.router)
app.include_router(payments.router)
app.include_router(admin.router)
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


# Where `npm run build` puts the frontend. Used by the PWA routes just below
# and by the single-origin SPA hosting further down.
_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


# ── PWA: service worker + manifest ────────────────────────────────────────
# Both live in frontend/public and so land in frontend/dist, where the SPA
# catch-all below would already serve them. They get explicit routes anyway for
# two reasons:
#   1. sw.js MUST NOT be cached. Cloudflare caches .js by default, and a stale
#      worker pins users to an old build until its cache expires.
#   2. The worker's scope is capped by its own path, so it has to be served
#      from the site root to control the whole app.
# Registered before the catch-all so these exact paths win.
_PWA_FILES = {
    "sw.js": "application/javascript",
    "manifest.json": "application/manifest+json",
}


def _pwa_file(name: str):
    path = _DIST / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(
        str(path),
        media_type=_PWA_FILES[name],
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


@app.get("/sw.js")
def service_worker():
    return _pwa_file("sw.js")


@app.get("/manifest.json")
def web_manifest():
    return _pwa_file("manifest.json")


# ── Single-origin hosting: serve the built frontend ───────────────────────
# After `npm run build`, frontend/dist exists and the backend serves the whole
# app, so ONE Cloudflare Tunnel exposes everything at a single URL. In dev
# (no dist) this block is skipped and you use the Vite dev server as before.
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
