# Revelator System Summary

## Research Capstone Documentation

Revelator is a web and mobile-capable application for screening document images for signs of forgery. A React client communicates with a FastAPI backend. The backend checks that an upload resembles a document, prepares the image, requests a structured classification from Google Gemini Vision, derives a verdict, and stores the scan in a SQLite database.

Revelator is a screening aid, not a substitute for a qualified forensic examiner. Results depend on image quality, available evidence, model behavior, and the user-provided image. A “no forgery detected” result is not proof of authenticity.

### System at a Glance

| Layer | Technology | Main responsibility |
|---|---|---|
| Client | React, Vite, Capacitor support | Sign-in, image submission, scan results, and history |
| API | FastAPI, Pydantic | Authentication, request validation, analysis, and application endpoints |
| Analysis | Gemini Vision, optional local classifier, document gate | Image screening and structured forgery-method classification |
| Persistence | SQLAlchemy, SQLite by default | User accounts, API-key records, scan metadata, and history |
| Evaluation | Specimen evaluation script | Compare predictions with labeled Forged/Genuine examples |

### Main Request Flow

1. An authenticated user chooses an image and submits it from the React client to `POST /api/analyze`.
2. The API opens the image, converts it to RGB, and checks whether it appears to be a document. A non-document receives an early response and is not saved as a scan.
3. The image is resized to a maximum dimension of 1280 pixels.
4. If enabled and available, the local classifier can provide a category hint. Gemini performs the classification. A low-confidence result may receive a second critique call.
5. The backend maps the category and confidence to a verdict, saves scan details and the uploaded image, and returns the result to the client.

```text
React client -> FastAPI analysis route -> document gate -> image preprocessing
            -> optional local hint -> Gemini Vision -> confidence review
            -> verdict mapping -> SQLAlchemy / SQLite -> scan result
```

The primary code path is implemented in `frontend/src/api/client.js`, `backend/app/routes/analyze.py`, and `backend/app/forgery/`.

<!-- PAGE BREAK -->

## Classification and Results

### Classification Categories

The classifier returns one category code, a confidence value, and explanatory fields such as evidence, reasoning, alternatives, and anomaly location. The taxonomy in `backend/app/forgery/gemini_vision.py` has 15 forgery-method categories and three fallback categories.

| Method group | Codes |
|---|---|
| Traced writing | `traced_carbon`, `traced_indentation`, `traced_projection` |
| Alteration | `addition_insertion`, `addition_interlineation`, `erasure_chemical`, `erasure_mechanical` |
| Digital manipulation | `digital_cut_paste`, `digital_desktop`, `digital_scanned` |
| Obliteration | `obliteration_ink`, `obliteration_whiteout` |
| Sympathetic writing | `sympathetic_indented`, `sympathetic_special` |
| Currency | `currency_analysis` |
| Fallbacks | `no_forgery_detected`, `not_a_document`, `other` |

Categories represent observed methods or signs. Specimen types without dedicated categories, such as charred or water-damaged documents, are routed to the closest available category or `other`.

### Verdict Mapping

The route converts Gemini’s category and confidence into the user-facing result. Explicit `not_a_document` and `no_forgery_detected` categories retain their meaning. Other classifications use confidence thresholds:

| Confidence | Verdict |
|---|---|
| 0.70 or higher | `forged` |
| 0.50 to below 0.70 | `suspicious` |
| Below 0.50 | `no_forgery_detected` |

These values are model-reported confidence scores and are not a calibrated probability of authenticity. The result should be treated as a screening signal for human review.

### Model Calls and Image Handling

The main Gemini request sends a resized JPEG together with the system prompt and optional user context. The configured model defaults to `gemini-2.5-flash`; the backend expects a JSON response. A confidence-gated critique runs only below 0.80 confidence, so it may add a second model call for uncertain cases. The optional local classifier is loaded from a separately trained model file; when unavailable, analysis continues through Gemini without the hint.

The document gate uses the configured Groq vision model when cloud screening is enabled and a Groq key is present; otherwise it attempts the configured Ollama model. If the gate cannot complete, it fails open and allows the image through to the main analysis rather than blocking the user.

<!-- PAGE BREAK -->

## Accounts, Data, and Application Structure

### Accounts and Access

The authentication routes support account registration, password login, token refresh, email verification, password reset, and Google sign-in. Passwords are hashed with bcrypt. Authenticated requests use signed JWT access tokens. Email-code two-factor authentication is configurable and applies to eligible password logins when email delivery is available. Users can save Gemini API keys to their accounts; the analysis route tries the user’s configured key records.

Google ID-token verification allows a small 10-second clock-skew tolerance to avoid rejecting otherwise valid tokens because of minor clock differences. Token signature, audience, issuer, and expiry verification remain in place.

### Data Storage

SQLAlchemy models define user accounts, saved API keys, login codes, trusted devices, scans, and audit records. SQLite is the default database. On Windows, the default data directory is under the user’s Local AppData folder; `REVELATOR_DATA_DIR` can override it. `DATABASE_URL` can select another SQLAlchemy-supported database.

Scan records store the verdict, confidence, detected category, explanation, evidence, timestamps, and image path. Uploaded scan images are saved separately from the database. Database files, API secrets, and uploaded documents are local/runtime data and are not included in the source appendix.

### Core Source Map

| File or directory | Purpose |
|---|---|
| `frontend/src/App.jsx` | Client routes and high-level application state |
| `frontend/src/api/client.js` | API requests, authentication headers, refresh behavior, and scan upload |
| `frontend/src/pages/` | Sign-in, scan, history, account, and other user-facing pages |
| `backend/app/main.py` | FastAPI app, middleware, route registration, and startup |
| `backend/app/routes/analyze.py` | Image-analysis endpoint, verdict mapping, and scan persistence |
| `backend/app/routes/auth.py` | Registration, login, Google sign-in, and account endpoints |
| `backend/app/auth.py` | Password, JWT, and authentication helpers |
| `backend/app/forgery/gemini_vision.py` | Category taxonomy, prompts, Gemini calls, and confidence review |
| `backend/app/forgery/document_gate.py` | Initial document/not-document screening |
| `backend/app/models.py` and `database.py` | Database schema and SQLAlchemy sessions |

<!-- PAGE BREAK -->

## Evaluation, Configuration, and Limitations

### Evaluation

`backend/evaluate_specimens.py` evaluates the classifier using labeled specimen images. Forged and Genuine labels provide the main verdict-level comparison; category-hit scoring checks whether the predicted method belongs to an accepted category set. The harness writes miss details and a machine-readable accuracy summary. Evaluation calls use real Gemini requests and require a configured API key, so sample sizes should be kept small unless token usage is understood.

Example commands:

```powershell
cd backend
python evaluate_specimens.py --sample 2
python evaluate_specimens.py --sample 5 --critique
```

The optional local classifier is trained separately with `backend/train_classifier.py`. Its model weights are not part of the source bundle. Without the weights, that optimization is skipped and the Gemini path remains available.

### Runtime Configuration

Backend variables are documented in `backend/.env.example`; frontend build variables are documented in `frontend/.env.example`. Common settings include the Gemini model and key, optional Groq/Ollama document-gate settings, database location, frontend API base, and authentication/email settings. Real credentials must be supplied locally and should not be placed in capstone documentation.

For local development, the backend entry point is `backend/run.py` and the frontend is built with Vite from `frontend/`. In the deployed web configuration, the backend can serve the built frontend from the same origin. The full frontend source is React; Capacitor/Android implementation files are intentionally omitted from this summary.

### Scope and Limitations

- Image focus, lighting, angle, compression, and resolution affect visible forensic cues.
- Some categories overlap visually, and a photograph cannot establish every physical property of the original document.
- Model confidence is not statistically calibrated; category and verdict accuracy must be measured against representative held-out data.
- The specimen set may not represent real-world documents or the full variety of forgery techniques.
- The application provides screening information, not a certified forensic conclusion.

### Primary References in the Project

The complete, copyable source listings are in `REVELATOR_COMPLETE_SOURCE.md`. The companion ZIP contains text files and required non-Android binary assets. This summary is an architectural guide; it does not replace the source code or deployment-specific configuration.