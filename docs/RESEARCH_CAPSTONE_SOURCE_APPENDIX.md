# Appendix: Core System Source Code

This appendix presents the essential source flow of Revelator. The listings are abridged documentation excerpts, not standalone replacement files. They omit interface styling, administrative screens, deployment configuration, and nonessential error handling. The complete implementation remains in the source files listed below.

## System Components

| Component | Main source | Responsibility |
|---|---|---|
| Web and mobile client | `frontend/src/App.jsx`, `frontend/src/api/client.js`, `frontend/src/pages/` | User interface, authentication state, image upload, and scan results |
| API server | `backend/app/main.py`, `backend/app/routes/` | HTTP endpoints, request validation, and application startup |
| Authentication | `backend/app/auth.py`, `backend/app/routes/auth.py` | Password hashing, JWT sessions, account flows, and API-key management |
| Analysis pipeline | `backend/app/routes/analyze.py`, `backend/app/forgery/` | Document gate, image preparation, classification, verdict, and scan persistence |
| Database | `backend/app/database.py`, `backend/app/models.py` | SQLite connection, ORM session, and persistent records |
| Vision model | `backend/app/forgery/gemini_vision.py` | Gemini Vision prompt, image request, and structured classification response |

## 1. API Application

Source: `backend/app/main.py`

```python
from fastapi import FastAPI

from .database import init_db
from .routes import admin, analyze, auth, payments, prompt_analytics

app = FastAPI(title="Revelator API")

app.include_router(auth.router)
app.include_router(analyze.router)
app.include_router(payments.router)
app.include_router(admin.router)
app.include_router(prompt_analytics.router)


@app.on_event("startup")
async def startup_event():
    init_db()
```

## 2. Database Connection

Source: `backend/app/database.py`

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
```

## 3. Persistent Data Models

Source: `backend/app/models.py` (selected fields)

```python
class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=True)
    role = Column(String, default="user", nullable=False)
    gemini_api_key = Column(String, nullable=True)


class Scan(Base):
    __tablename__ = "scans"

    id = Column(String, primary_key=True, default=gen_uuid)
    scan_id = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    filename = Column(String, nullable=False)
    verdict = Column(String, nullable=False)
    confidence_score = Column(Float, nullable=False)
    detected_category = Column(String, nullable=True, index=True)
    category_explanation = Column(Text, nullable=True)
    image_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

## 4. Authentication

Source: `backend/app/auth.py` (selected functions)

```python
def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def create_access_token(user_id: str) -> str:
    expires = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": user_id, "exp": expires, "type": "access"},
        SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


async def get_current_user(token=Depends(oauth2_scheme), db=Depends(get_db)):
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user
```

## 5. Image Classification

Source: `backend/app/forgery/gemini_vision.py` (selected functions)

```python
def preprocess_image(image: Image.Image) -> Image.Image:
    max_dimension = 1280
    width, height = image.size
    if max(width, height) > max_dimension:
        scale = max_dimension / max(width, height)
        image = image.resize(
            (int(width * scale), int(height * scale)),
            Image.LANCZOS,
        )
    return image.convert("RGB") if image.mode != "RGB" else image


def classify(image, document_type=None, api_key=None):
    client = _client(api_key=api_key)
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=88)

    response = client.models.generate_content(
        model=GEMINI_VISION_MODEL,
        contents=[
            SYSTEM_PROMPT,
            genai_types.Part.from_bytes(
                data=buffer.getvalue(),
                mime_type="image/jpeg",
            ),
        ],
        config=genai_types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )
    return json.loads(response.text)
```

## 6. Verdict Mapping

Source: `backend/app/routes/analyze.py` (condensed)

```python
def _verdict_from_gemini(result):
    category = result["category"]
    confidence = result["confidence"]

    if category == "not_a_document":
        return "not_a_document", confidence
    if category == "no_forgery_detected":
        return "no_forgery_detected", confidence
    if confidence >= 0.70:
        return "forged", confidence
    if confidence >= 0.50:
        return "suspicious", confidence
    return "no_forgery_detected", confidence
```

## 7. Scan Request and Persistence

Source: `frontend/src/api/client.js` and `backend/app/routes/analyze.py` (condensed)

```javascript
analyze(file, category, documentType, extras = {}) {
  const form = new FormData();
  form.append('imageFile', file);
  if (category) form.append('category', category);
  if (documentType) form.append('document_type', documentType);
  return request('/analyze', { method: 'POST', body: form });
}
```

```python
is_document, reason = check_is_document(image)
if not is_document:
    return {"verdict": "not_a_document", "llm_explanation": reason}

prepared = preprocess_image(image)
result = gemini_classify(prepared, document_type=document_type, api_key=api_key)
review = confidence_gated_analyze(prepared, {}, result, api_key=api_key)
result = review["result"]
verdict, confidence = _verdict_from_gemini(result)

scan = Scan(
    scan_id=generate_scan_id(),
    user_id=current_user.id,
    filename=imageFile.filename or "unknown",
    verdict=verdict,
    confidence_score=confidence,
    detected_category=result["category"],
    category_explanation=result["explanation"],
)
db.add(scan)
db.commit()
```

The scan route also supports per-user API-key selection, optional local-classifier hints, image-file storage, user-provided context, and provider-error handling. Those branches are omitted here to keep the listing focused; the complete implementation is in `backend/app/routes/analyze.py`.

## Complete Source

The selected listings above show the primary scan path. The full application also includes registration and login, email verification and two-factor authentication, scan history, account settings, administrative tools, payment endpoints, prompt analytics, and mobile/PWA support. These are implemented in `backend/app/routes/`, `backend/app/forgery/`, and `frontend/src/`.