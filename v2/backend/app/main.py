"""FastAPI entrypoint for Revelator v2."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import APP_NAME, APP_VERSION, FRONTEND_URL
from .firebase_admin_init import init as firebase_init
from .routes import analyze, payments


@asynccontextmanager
async def lifespan(_: FastAPI):
    firebase_init()
    yield


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze.router)
app.include_router(payments.router)


@app.get("/")
def root():
    return {"name": APP_NAME, "version": APP_VERSION, "status": "ok"}
