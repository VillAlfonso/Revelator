# Revelator - Engineering Reference & Change Log

Forensic document forgery detection. FastAPI backend + React/Capacitor frontend.
Primary classifier is Google Gemini Vision, run BYOK (each user supplies their own
Gemini API key). This file is the living map of the system and a dated log of the
changes made while tuning it.

> Style rule for this repo: never use the em-dash character. Use "->", parentheses,
> colons, or commas.

---

## 1. What happens on a scan (request flow)

`POST /api/analyze` (see `backend/app/routes/analyze.py`):

```
upload image
  -> check_is_document()         cheap yes/no gate (Groq or Ollama); non-documents
                                 return a friendly reply and are not charged/saved
  -> preprocess_image()          resize longest side to 1280px, RGB
  -> gemini_classify()           full system prompt, all 19 categories, structured JSON
  -> confidence_gated_analyze()  self-critique ONLY when confidence < 0.80
  -> _verdict_from_gemini()      map (category, confidence) -> forged/suspicious/clean
  -> persist Scan row + return result
```

The image goes to Gemini once on the main pass, and a second time only when the
critique fires (low confidence). Everything the user sees (category label, evidence,
reasoning, alternatives, anomaly location) comes from that single main JSON response.

Model: `GEMINI_VISION_MODEL` (default `gemini-2.5-flash`). If unset, a fallback chain
`pro -> flash -> flash-lite` is tried on rate-limit errors only. Temperature 0.2,
`response_mime_type=application/json`.

---

## 2. The taxonomy (source of truth: `backend/app/forgery/gemini_vision.py` CATEGORIES)

15 forgery-method categories (detecting one == a forgery/tampering sign was found):

| Group        | Codes |
|--------------|-------|
| traced       | traced_carbon, traced_indentation, traced_projection |
| alteration   | addition_insertion, addition_interlineation, erasure_chemical, erasure_mechanical |
| digital      | digital_cut_paste, digital_desktop, digital_scanned |
| obliteration | obliteration_ink, obliteration_whiteout |
| sympathetic  | sympathetic_indented, sympathetic_special |
| currency     | currency_analysis |

Fallbacks: `no_forgery_detected`, `not_a_document`, `other`. Total 18 codes.
(obliteration_pigment / "Opaque Pigment" was removed 2026-07-04, front end to back end.)

This is the intended, fixed taxonomy. The specimen set (below) also contains folders
for Charred, Water-Soaked, Paper-Fold, Embossing, Typewriting-ID, and Contact-Writing;
by decision these are NOT added as categories - the classifier routes them to the
closest existing code or to `other`. The frontend `frontend/src/categories.js` and the
`/api/about` marketing stats are a separate presentation layer; `/api/about` dataset
counts and model names are demo decoration and intentionally do not mirror this
taxonomy, so do not "fix" them.

### Specimen folder -> expected code map (used by the eval harness)

| SPECIMEN PICTURES folder            | Expected code(s) |
|-------------------------------------|------------------|
| ADDITION                            | addition_insertion, addition_interlineation |
| CHARRED DOCUMENTS                   | other (no dedicated category) |
| CONTACT WRITING                     | other, traced_carbon |
| COUNTERFEITED-FALSIFIED DOCUMENTS   | currency_analysis, digital_*, addition_insertion, erasure_* (heterogeneous) |
| EMBOSING PRINT                      | other (no dedicated category) |
| ERASURE (CHEMICAL / MECHANICAL)     | erasure_chemical / erasure_mechanical |
| INDENTED WRITINGS                   | sympathetic_indented, traced_indentation |
| MODERN FORGERY (CUT&PASTE/DTP/SCAN) | digital_cut_paste / digital_desktop / digital_scanned |
| OBLITERATED WRITING                 | obliteration_ink, obliteration_whiteout |
| PAPER FOLD                          | other (no dedicated category; also lacks Forged/Genuine split) |
| SECRET WRITING                      | sympathetic_special |
| TRACED FORGERY (CANAL/CARBON/TRANS) | traced_indentation / traced_carbon / traced_projection |
| TYPEWRITING IDENTIFICAITON          | other (no dedicated category) |
| WATER SOAKED DOCUMENTS              | other (no dedicated category) |

Each folder has `Forged/` and `Genuine/` subfolders (PAPER FOLD does not, so the harness
skips it). Forged/Genuine is the most reliable label: Forged -> expect verdict forged or
suspicious; Genuine -> expect no_forgery_detected. Category-hit is scored against the
acceptable set above.

---

## 3. Every endpoint

Health: `GET /api/health`

Analysis (`backend/app/routes/analyze.py`, prefix `/api`):
- `GET  /api/document-types`
- `GET  /api/about`
- `POST /api/analyze`
- `GET  /api/history`
- `GET  /api/history/{scan_id}`
- `PUT  /api/history/{scan_id}/notes`
- `GET  /api/history/{scan_id}/image`

Prompt analytics (`routes/prompt_analytics.py`, prefix `/api`):
- `GET  /api/prompt-analysis`  (admin PromptDashboard; static snapshot, kept in sync
  with the gemini_vision.py prompt by hand)

Auth (`routes/auth.py`, prefix `/api/auth`):
- `POST /register`, `POST /login`, `POST /refresh`, `GET /verify-email`,
  `POST /resend-verification`, `POST /forgot-password`, `POST /reset-password`,
  `POST /google`, `GET /me`, `PUT /me`, `PUT /api-key`, `GET /api-keys`,
  `POST /api-keys`, `DELETE /api-keys/{key_id}`, `PUT /api-keys/{key_id}/activate`,
  `PUT /api-keys/{key_id}`

Admin (`routes/admin.py`, prefix `/api/admin`):
- `GET /stats`, `GET /users`, `GET /users/{id}`, `PUT /users/{id}`,
  `DELETE /users/{id}`, `GET /super/info`, `POST /super/promote`,
  `GET /gemini-status`, `POST /users/{id}/ban`, `POST /users/{id}/unban`,
  `POST /users/{id}/promote-admin`, `POST /users/{id}/demote-admin`,
  `GET /super/logs`, `GET /scans/{scan_id}/image`

Roles (`routes/roles.py`, prefix `/api/roles`):
- `GET ""`, `POST ""`, `PUT /{role_id}`, `DELETE /{role_id}`, `PUT /users/{user_id}/role`

Rooms/classrooms (`routes/rooms.py`, prefix `/api/rooms`):
- `GET ""`, `POST ""`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}`,
  `POST /{id}/regenerate-code`, `DELETE /{id}/members/{user_id}`,
  `GET /mine/list`, `POST /join`

Payments (`routes/payments.py`, prefix `/api/payments`) - decorative for the capstone:
- `GET /plans`, `POST /create-checkout`, `POST /webhook`, `GET /verify-session`,
  `POST /cancel`, `POST /paymongo-checkout`, `POST /paymongo-webhook`,
  `GET /paymongo-public-key`

---

## 4. Token / cost notes

- Scans are unlimited in the capstone (`check_scan_limit` never blocks). "Minimal
  tokens" therefore means minimizing per-scan cost, not enforcing a quota.
- The redundant triage pre-pass was removed (2026-07-04). It was a whole extra Gemini
  vision call (own prompt + a re-sent image) whose only output fed the "alternatives"
  list that the main classification already produces. Removing it drops one full vision
  round-trip per scan with no user-visible change. This is the clean token win.
- The document gate (`check_is_document`) and the low-confidence self-critique are kept.
  The critique fires only when confidence < 0.80; its threshold lives in
  `confidence_gated_analyze(threshold=0.80)` and is safe to tune.
- Biggest remaining lever if further cuts are needed: the system prompt is ~2,850 words
  and re-sent every scan. Gemini 2.5 implicit-caches a shared static prefix, so
  multi-scan sessions already pay less. Compressing the longest category blocks
  (traced_projection, addition_insertion, erasure_mechanical) would help single cold
  scans; use the eval harness to confirm no accuracy regression before/after.

---

## 5. Evaluation harness

`backend/evaluate_specimens.py` runs the classifier against the labeled SPECIMEN PICTURES
set and scores it, so prompt/pipeline changes can be measured instead of guessed at.

```
cd backend
python evaluate_specimens.py --sample 2          # 2 imgs per (folder,label): cheap smoke test
python evaluate_specimens.py --sample 10 --category ERASURE
python evaluate_specimens.py --sample 5 --critique   # include the low-confidence critique pass
```

Needs `GEMINI_API_KEY` in the environment / `.env` (BYOK: the server key is blank by
design, so set one before running). Every run spends real tokens, so it defaults to a
tiny sample. Output: a console table (per-folder forged/genuine accuracy + category-hit),
a CSV of misses (`specimen_misses.csv`), and a machine-readable summary at
`backend/app/data/specimen_accuracy.json`.

---

## 6. Live accuracy dashboard

The harness writes `backend/app/data/specimen_accuracy.json` on every run. It is served
by `GET /api/prompt-analysis/accuracy` (returns `{"status":"no_data"}` until the first
run). Two front ends poll it and update on their own:
- React admin dashboard `frontend/src/components/PromptDashboard.jsx` -> "System
  Accuracy" tab (polls every 15s).
- Standalone `backend/PROMPT_ANALYSIS.html`: a "Live System Accuracy" banner at the top
  (polls every 15s; fetches same-origin or `http://localhost:8000`).

So "real-time accuracy" = re-run the harness, and both dashboards refresh within 15s.

---

## 7. Review + recommendations (what to change/add to improve accuracy)

Grounded in a full read of the prompt and a look at the specimen set. The eval harness
turns each of these into a measurable before/after once a GEMINI_API_KEY is available.

1. Prompt-mass imbalance (the dashboard's own headline). Category detail ranges from
   ~500 words (addition_insertion) to ~5 (obliteration_ink, obliteration_whiteout,
   currency_analysis). Thin categories lose ties because the model has no cues. Bring
   each thin category up to ~40-80 words of concrete visible indicators:
   - obliteration_ink: IR-recoverable ghost, scribble stroke direction, ballpoint vs marker sheen.
   - obliteration_whiteout: raised chalky texture, brush/roller edges, off-white vs paper, new text on top.
   - currency_analysis: watermark, security thread, microprint, intaglio relief, serial-number font, color-shift ink; add Philippine-peso specifics for this capstone.
   - sympathetic_indented: raking-light shadow stripes, no ink in the grooves, pressure from a sheet above.
2. Unaddressed overlap: sympathetic_indented vs traced_indentation (both grooves). Add
   one explicit DISTINCTION block: sympathetic = grooves WITHOUT ink; traced = grooves
   WITH ink filling them.
3. False positives on genuine documents. Every specimen folder has a Genuine set; a
   prompt primed to "find forgery" tends to over-flag. Measure Genuine accuracy first,
   then strengthen the "when in doubt -> no_forgery_detected" guidance.
4. Confidence calibration. Verdict thresholds (0.70 forged / 0.50 suspicious) use the
   model's raw self-reported confidence, which is not calibrated. Use the miss CSV to fit
   thresholds to observed error rates.
5. Local context (capstone): peso notes, Barangay / PSA / NBI / LTO document formats and
   their real seals and typefaces. The embossing specimen was a Barangay certificate.

Highest-leverage ADDITION: reference-image few-shot. Gemini accepts multiple images, so
attaching 1-2 canonical examples for the thin/hard categories (a real dry seal vs a
printed one, a genuine vs counterfeit peso) would raise accuracy more than more prose.
Cost is extra input tokens per call; measure the trade with the harness.

Bigger re-approach options (only if the single-call approach plateaus):
- Evidence-first structured prompting: force the model to list regions/textures/anomalies
  as structured observations BEFORE classifying (reduces hallucination).
- A thin calibration layer: learn (category, raw_confidence) -> calibrated probability
  from the specimen results. Cheap; improves verdicts without touching the prompt.
- Keep the pipeline single-call: it is already near-optimal for tokens. Do NOT re-add a
  triage/ensemble pass unless the harness proves it pays for itself.

---

## Change log

### 2026-07-04 - Remove opaque-pigment category + live accuracy dashboard
- Removed `obliteration_pigment` ("Opaque Pigment") end to end: gemini_vision.py
  (taxonomy, prompt, detail, group map, triage list, overlaps, clue label),
  document_types.py, prompt_analytics.py, PROMPT_ANALYSIS.html, categories.js, Scan.jsx
  (clue option), ForensicsGuide.jsx. Now 15 forgery methods + 3 fallbacks = 18 codes.
  (Old scan rows with this category still display via label lookup; no migration done.)
- Added live accuracy: evaluate_specimens.py writes app/data/specimen_accuracy.json;
  new endpoint GET /api/prompt-analysis/accuracy; a "System Accuracy" tab in the React
  PromptDashboard and a "Live System Accuracy" banner in PROMPT_ANALYSIS.html, both
  polling every 15s.
- BLOCKED: could not run the real specimen evaluation - no GEMINI_API_KEY is configured
  (BYOK; server key blank, no user keys in DB). Set a key, then run
  `cd backend && python evaluate_specimens.py --sample 3` to populate the dashboards.

### 2026-07-04 - Token trim + eval harness
- Removed the redundant triage Gemini call from `/api/analyze` (its output only seeded
  alternatives the main pass already returns). One fewer vision round-trip per scan.
  The document gate and the low-confidence critique were left unchanged.
- Added `backend/evaluate_specimens.py`, a scored harness over the specimen set.
- Added this `CLAUDE.md`.
- Explored expanding the taxonomy to cover the 6 specimen-only categories (Charred,
  Water-Soaked, Paper-Fold, Embossing, Typewriting-ID, Contact-Writing); reverted at
  the maintainer's request. Taxonomy stays at the original 16 forgery methods + 3
  fallbacks. The harness treats those 6 folders as `other`.
