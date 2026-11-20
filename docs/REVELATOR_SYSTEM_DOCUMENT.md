# Revelator System Document

This document is based on the current workspace in `C:\Revelator` and the system files and configuration already present in the project. It summarizes what the system does, how it is built, how the main components connect, and how this project is organized on this machine.

## 1. System Overview

Revelator is a document-forgery screening system for analyzing uploaded document images and identifying likely signs of alteration, tracing, cut-and-paste manipulation, erasure, and other suspicious document changes. It is designed as a decision-support tool, not an absolute forensic authority.

The system is built around:

- A React frontend for user interaction
- A FastAPI backend for analysis, auth, and data management
- AI-based visual inspection using Gemini Vision and optional secondary model checks
- A document gate to determine whether an uploaded image is actually a document
- SQLite-based persistence for user records, scan history, and analysis results
- Support for mobile packaging via Capacitor and a local Windows-based runtime

The project is currently located under:

- Workspace root: `C:\Revelator`
- Backend: `C:\Revelator\backend`
- Frontend: `C:\Revelator\frontend`
- Documentation: `C:\Revelator\docs`
- Sample evidence: `C:\Revelator\Samples`
- Support tooling: `C:\Revelator\tools`

## 2. Operating Environment and Local Context

From the current system layout, this project is running in a Windows-based environment and is organized as a local software project with a Python backend and JavaScript frontend.

Relevant local runtime artifacts include:

- `start.bat` — launches the backend and frontend together
- `host-revelator.bat` — likely used for hosting or local run setup
- `rebuild-web.bat` — rebuilds frontend assets
- `venv` — local Python virtual environment under the project

The local startup script confirms the intended development flow:

- Backend at `http://localhost:8000`
- Frontend at `http://localhost:5173`

This means the application is intended to run as a local development stack that can be launched from the project root using the provided Windows batch files.

## 3. Project Goal

The system supports the following broad workflow:

1. User uploads an image of a document.
2. The backend validates that the image resembles a document.
3. The image is preprocessed for analysis.
4. AI models inspect the image for forgery indicators.
5. The system classifies the issue into a forgery category or declares no forgery detected.
6. Results are stored and shown to the user.
7. The system provides a screening result, not legal or forensic final proof.

The project is essentially a forensic-document screening application that tries to identify manipulations in scanned, printed, or photographed documents, such as IDs, licenses, receipts, forms, and certificates.

## 4. System Architecture

### 4.1 Frontend Layer

The client layer is implemented in React with Vite and is designed for web use with optional mobile support using Capacitor.

From the project metadata:

- React 18
- Vite 5
- Capacitor Android integration
- Ionic-style component support (`@ionic/pwa-elements`)
- Google auth support
- Camera/file access helpers

This frontend is responsible for:

- User sign-in and registration
- Uploading document images
- Connecting to the backend API
- Displaying analysis results
- Showing scan history and account information

Relevant frontend folders:

- `frontend/src/`
- `frontend/public/`
- `frontend/android/`

### 4.2 Backend API Layer

The backend is a FastAPI application. The project summary and `backend/app/main.py` show that the core API provides:

- Authentication endpoints
- Analysis endpoints
- Admin endpoints
- Health checks
- Payments endpoints
- Prompt analytics and intercept routes

The backend also handles:

- CORS policies
- Security headers
- Request validation
- JWT-based access and refresh tokens
- User records and login session management
- File storage for uploaded scans

The FastAPI app is explicitly described as a "forensic document forgery detection SaaS" API.

### 4.3 AI and Classification Layer

The central AI logic is in:

- `backend/app/forgery/gemini_vision.py`
- `backend/app/forgery/document_gate.py`

The project uses a classification taxonomy with categories such as:

- Traced writing
- Alteration and erasure
- Cut-and-paste digital manipulation
- Desktop publishing forgery
- Scanned document forgery
- Obliteration
- Sympathetic ink indicators
- Currency forgery
- Fallback cases like `no_forgery_detected` and `not_a_document`

The system prompt in the Gemini classifier is designed to minimize false positives by requiring specific visible evidence before declaring a forgery. It prioritizes authenticity unless there is clear tampering evidence.

AI behavior includes:

- Preprocessing image input
- Optional local classifier hints
- Gemini Vision analysis with structured JSON output
- Confidence review and critique on uncertain results
- Mapping model output into a user-facing verdict

### 4.4 Data and Persistence Layer

The project stores analysis data in a SQLAlchemy-backed database, defaulting to SQLite.

The system tracks:

- User accounts
- Saved API keys
- Login codes and devices
- Uploaded scans
- Verdicts and confidence scores
- Explanation and evidence fields
- Account and event metadata

The database is intended to be local by default, and the project documents note that data directories can be overridden through environment variables such as `REVELATOR_DATA_DIR` and `DATABASE_URL`.

Uploaded images are saved separately from the database records, which improves separation between metadata and raw file artifacts.

## 5. Main Processing Flow

The core request flow described in the project summary is:

1. User submits image from frontend.
2. Backend checks if image is a document.
3. Image is resized and normalized.
4. Optional local classifier may provide a hint.
5. Gemini Vision classifies the image into a forgery category.
6. Confidence is mapped to a verdict.
7. Result is stored in database and returned to client.

Conceptually:

`React client -> FastAPI analysis route -> document gate -> preprocessing -> optional local hint -> Gemini -> verdict -> database`

This is the main use case that transforms an input document image into a forensic classification result.

## 6. Classification Logic

The system does not simply label images as forged or genuine based on general appearance. It uses a structured taxonomy designed around document examination methods.

Major categories in the system include:

- `traced_carbon`
- `traced_indentation`
- `traced_projection`
- `addition_insertion`
- `addition_interlineation`
- `erasure_chemical`
- `erasure_mechanical`
- `digital_cut_paste`
- `digital_desktop`
- `digital_scanned`
- `obliteration_ink`
- `obliteration_whiteout`
- `sympathetic_indented`
- `sympathetic_special`
- `currency_analysis`
- `no_forgery_detected`
- `not_a_document`
- `other`

The verdict is then mapped to a simpler user-facing output:

- High confidence: `forged`
- Moderate confidence: `suspicious`
- Low confidence: `no_forgery_detected`

This means the app is designed around a screening signal rather than absolute certainty.

## 7. Authentication and Security

The backend includes a robust authentication layer. Based on the code and project docs:

- Passwords are hashed with bcrypt
- JWT access tokens are used for authenticated requests
- Refresh tokens are supported
- Google sign-in is supported
- Email verification and reset flows are present
- Trusted-device and two-factor login support exists in the codebase

The application also includes request-level security checks such as:

- Cross-site request blocking
- CORS enforcement
- Security headers
- No-store cache behavior for API responses
- CSP restrictions

This indicates the project treats backend API security as important, especially because it accepts user uploads and stores account information.

## 8. Local Repository Structure and Main Files

The repository contains both the product and supporting analysis/documentation resources.

### Key folders

- `backend/` — backend source, AI classification, database, training, evaluation
- `frontend/` — UI and web app source
- `docs/` — research, summary, and project documentation
- `Samples/` — sample document images used for template/dataset evaluation
- `conceptual-model/` — concept or design artifacts
- `tools/` — tunnel, startup, configuration support scripts
- `forgeguard-v2/` — secondary variant or related app snapshot

### Key files

- `start.bat` — local startup entry point
- `backend/app/main.py` — FastAPI app initialization and routers
- `backend/app/routes/analyze.py` — main analysis endpoint
- `backend/app/routes/auth.py` — authentication routes
- `backend/app/auth.py` — JWT and auth helpers
- `backend/app/forgery/gemini_vision.py` — main classification model logic
- `backend/app/forgery/document_gate.py` — document detection gate
- `backend/requirements.txt` — backend dependencies
- `frontend/package.json` — frontend dependencies and scripts
- `docs/REVELATOR_SYSTEM_SUMMARY.md` — system-level summary
- `docs/REVELATOR_COMPLETE_SOURCE.md` — detailed source code snapshot

## 9. Startup and Execution Model

The project is intended to run locally with a Windows batch launcher. The script at `start.bat` starts both services:

- Python backend: `backend/run.py`
- Frontend Vite app: `frontend/npm run dev`

The expected local endpoints are:

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`

This suggests a standard local development architecture where a human operator can run the system on one PC, upload images, and review results in the browser.

## 10. Limitations and Interpretation

The project documentation clearly states the system is a screening aid, not a substitute for a qualified forensic examiner.

Important limitations include:

- Results depend on image quality
- Model behavior can vary
- Some categories are approximate
- A “no forgery detected” result is not proof of authenticity
- The system should be treated as supporting evidence for human review

This aligns with the intended use of the tool as a decision-support application for suspicious documents, not as a final legal or forensic authority.

## 11. Conclusion

This project is a document-forgery analysis platform built for local use on a Windows machine. It combines a modern React frontend, a Python FastAPI backend, structured authentication, database persistence, and AI-based document analysis using Gemini and support models.

The system is designed to classify a document image into a forgery category, provide confidence-based verdicts, and save the result for later review. In practical terms, it is a document forensic assistance tool that helps detect manipulated or suspicious records and supports human examination.

Its value lies in combining image review, classification logic, and organized evidence capture into one workflow that can run from a local developer machine or a be deployed environment.
