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

### 2026-07-10 - Currency false-positive fix, prompt-analytics sync, desktop burger removal, downloadable APK
- Root problem reported: genuine banknotes were being flagged as forged via
  `currency_analysis`. Cause was two-fold: (1) the `currency_analysis` prompt block was
  ~5 words ("Suspected counterfeit banknote."), so the model had no way to tell genuine
  from counterfeit and defaulted to flagging; (2) the local classifier's "counterfeit"
  class hinted `currency_analysis` with a prejudicial label ("a counterfeit / falsified
  document") that primed the short explain-only pass to confirm counterfeit even on real
  money. Note: a groupmate had described similar fixes, but none of his work was ever
  pushed to this repo (checked all local + origin branches), so these were reimplemented
  and reviewed here rather than merged.
- Fix (all prompt-level, no extra API calls, ~180 words added to a statically-cached
  prefix so token cost is negligible):
  - `gemini_vision.py`: expanded the `currency_analysis` block to ~200 words with concrete
    COUNTERFEIT signs (no raised intaglio relief, watermark/thread printed-on or missing,
    blurry microprint, photocopy dot rosettes, non-shifting colour-shift ink, wrong-font
    or mismatched serials) and GENUINE signs, plus Philippine-peso (BSP) specifics.
    Added a top-level `⚠ GENUINE CURRENCY RULE`: real money is not a forgery, use
    `currency_analysis` only with a specific counterfeit sign, else `no_forgery_detected`.
    Mirrored the same detail into `CATEGORY_DETAIL["currency_analysis"]`.
  - Strengthened `EXPLAIN_PROMPT_TEMPLATE` with a GENUINE BIAS + CURRENCY caution (the
    classifier only narrows, judge from the image, authentic -> no_forgery_detected).
  - `local_classifier.py`: neutralized the "counterfeit" label to
    "a banknote or official document (verify authenticity)".
  - Gemini's raw `explanation` already flows straight into the result description
    (`category_explanation = gemini["explanation"]`, no post-processing); left intact.
- Prompt analytics synced to the new block: `routes/prompt_analytics.py` and
  `PROMPT_ANALYSIS.html` currency entries updated (word_count 5 -> 203, detail VERY LOW
  -> HIGH, real indicators, a currency_analysis vs no_forgery_detected distinction);
  stale SYSTEM_PROMPT word/char count refreshed. The live analyzer (`analyze_prompts()`)
  picks up the new block automatically.
- Desktop burger removal: the burger is the ONLY nav on phone widths and inside the APK
  (the horizontal `.nav-desktop` bar is hidden there), so it was NOT removed outright.
  Lowered the switch-over breakpoint 900px -> 767px in index.css so tablets/laptops/desktop
  show the nav bar (no burger), while true phone widths and the Android app keep the
  burger. Added a compaction rule for the 768-991px range so the extra items fit.
- Downloadable APK: built the debug APK (Android Studio JBR as JAVA_HOME, SDK 34).
  The web bundle bakes the API base at build time, so the APK needs the ABSOLUTE base
  (it loads from localhost) while the hosted web bundle stays RELATIVE `/api` (same-origin).
  Process: build web with VITE_API_URL=https://revelator.site (temporarily move
  `.env.production.local` aside so `.env` wins) -> `npx cap sync android` ->
  `android/gradlew assembleDebug` -> copy `app-debug.apk` to `backend/downloads/revelator.apk`
  -> restore env and rebuild web (relative). New backend route `GET /download/revelator.apk`
  (registered before the SPA catch-all, media type application/vnd.android.package-archive,
  attachment disposition). Login.jsx shows a "Download Android App (.apk)" button on web
  only (hidden on native). The APK and `android/local.properties` are gitignored like the
  `.pt` model. Verified via TestClient: route returns 200, 9.2MB, correct headers.
  NOTE: backend changes (download route + currency prompt) require a server restart to go
  live; the static web bundle is already served fresh from disk.

### 2026-07-10 (second pass) - Synthesized the groupmate's currency work from forgeguard-v2, live-validated
- Correction to the note above: the groupmate's work DOES exist, in a separate checkout at
  `C:\Revelator\forgeguard-v2` (its own git repo, not a branch here). Reviewed his
  gemini_vision.py: a ~12,600-word SYSTEM_PROMPT (2.8x ours) with a full genuine-bias
  reasoning framework (AUTHENTICITY FIRST, DIRECT/PARTIAL/INFERRED observability, category
  evidence scoring, hallucination prevention, tie-breaking) and a very detailed Philippine
  banknote (BSP) currency block with NGC/NDS series awareness and UV handling. He also
  removed the local classifier (pure Gemini) and RE-ADDED the triage pre-pass (an extra
  vision call). His `category_explanation = gemini["explanation"]` is identical to ours, so
  "Gemini response straight to the description" was already true here.
- Per the "max accuracy + MIN tokens" goal, did NOT adopt his prompt wholesale (it is
  ~22K tokens/scan) or re-add his triage call. Instead: distilled his currency
  discriminators into our block (now 355 words / VERY HIGH): NGC and NDS both legal tender,
  the "security features PRESENT but SIMULATED (flat/printed/sticker-like) = counterfeit"
  test, and the genuine-note photo caveat (blur/wear/fade/low-light alone != counterfeit).
  Net SYSTEM_PROMPT ~4,720 words / ~8.3K tokens (38% of his).
- Key structural fix (analyze.py): the specimen local_classifier routes ANY banknote to its
  "counterfeit" class at ~1.0 conf, and the terse explain-only prompt cannot tell genuine
  from fake. So currency hints now SKIP the explain-only shortcut and fall through to the
  full prompt (which carries the genuine-vs-counterfeit discriminators). Only currency
  images pay for the full prompt; other categories keep the explain-only token saving.
- Tried adding a cross-category "EVIDENCE DISCIPLINE" genuine-bias block (distilled from his
  framework) but REMOVED it: it was unvalidated across the other 14 categories, added tokens,
  and the currency block already fixes the currency false positive on its own.
- Live-validated with the user's Gemini keys (from API_KEYS.md, gitignored) against the
  SPECIMEN PICTURES/.../PHILIPPINE CURRENCY set on gemini-2.5-flash: genuine notes
  (100/200/500/1000) reliably return no_forgery_detected (the reported false positive is
  fixed), clear fakes are caught as currency_analysis/forged; borderline fakes (a
  design-correct multi-note sheet, a genuine-looking macro crop, a moderate ~1000 repro
  whose only tell is a simulated thread) are inconsistent at temperature 0.2. That
  precision/recall trade is intentional: tightening to catch borderline fakes reintroduces
  the false positives on real money that were the actual complaint. (Free-tier keys are
  quota-limited, ~a handful of scans each; "other/0.0" verdicts in testing were quota
  failures, not real classifications.)
- APK NOT reassembled: this pass changed backend only. The prompt runs server-side; the
  installed APK and the website both call the same backend, so the currency improvements
  apply after a backend restart with no new APK build. Prompt-analytics py + html currency
  entries and the SYSTEM_PROMPT word/char counts were synced.

### 2026-07-07 - Email-OTP 2FA, auto-start hosting, light-mode drawer fix
- Added two-factor sign-in (email code). Password login now returns
  `{requires_2fa:true, email, message}` instead of tokens when 2FA applies; the client
  finishes at `POST /api/auth/verify-2fa` (email + 6-digit code + remember_device).
  New: `POST /api/auth/resend-2fa`, `PUT /api/auth/2fa` (per-user toggle; surfaced in
  Account -> Security). Backend: `LoginCode` + `TrustedDevice` tables (create_all),
  `users.two_factor_enabled` column (ensured in database.py), auth helpers
  `generate_otp_code`/`generate_device_token`/`hash_token` (sha256), email template
  `send_2fa_code_email`. Config: `TWO_FACTOR_ENABLED` (default on),
  `TWO_FACTOR_CODE_TTL_MINUTES` (10), `TWO_FACTOR_MAX_ATTEMPTS` (5),
  `TRUSTED_DEVICE_DAYS` (30). Codes are stored hashed, one live code per user, expiry +
  attempt-capped; trusted-device tokens (stored hashed, per-email in localStorage) skip
  the code for 30 days. Guardrails: only enforced when SMTP is configured (else login
  falls through so nobody is locked out), Google logins exempt, signup still auto-logs in.
  Frontend: Login.jsx gains a code-entry stage; client.js `verify2fa/resend2fa/setTwoFactor`
  + per-email device-token storage. Verified end-to-end (12/12 checks) against the live
  server, then DB cleaned of test users.
- Light-mode drawer bug: tapping the burger in light mode looked like the screen went
  blank. Cause: the drawer kept its dark background while light-theme CSS remapped its
  text to dark (dark-on-dark = invisible) and the backdrop's rgba(0,0,0,0.6) veil
  darkened the whole light page. Fix in App.jsx: drawer panel + backdrop veil are now
  theme-aware (`isLight = theme==='light'`) - white drawer surface + soft light veil so
  the page just blurs, matching dark mode.
- Easy hosting: `tools/revelator-startup.vbs` launches host-revelator.bat hidden; a copy
  lives in the per-user Startup folder so the server + tunnel auto-start at login.
  host-revelator.bat now uses `start /min`. Manual double-click still works. Delete the
  Startup copy to stop auto-hosting. (Google sign-in still needs the account owner to add
  https://revelator.site to the OAuth client's Authorized JavaScript origins - console-only.)

### 2026-07-06 - Live on revelator.site (named Cloudflare tunnel)
- Domain revelator.site bought at Namecheap, nameservers moved to a free Cloudflare
  account (zone Active). This replaces the account-less quick tunnel (random URL +
  Safe-Browsing "Dangerous" flag) with a stable custom domain and a real cert.
- Named tunnel "revelator" (id ac5f952f-02ad-457d-8d2d-64cafbc359ec). One-time setup:
  `cloudflared login` -> `tunnel create revelator` -> `tunnel route dns --overwrite-dns
  revelator revelator.site` (and www). Had to delete Namecheap's imported apex A record
  first; --overwrite-dns clobbers a same-type record but not a leftover parking A at the
  apex, so that one deletion was manual in the Cloudflare DNS dashboard.
- Config at %USERPROFILE%\.cloudflared\config.yml: tunnel id + credentials-file +
  ingress (revelator.site and www.revelator.site -> http://localhost:8010, else 404).
  Credentials json lives beside it (secret, machine-local, not in repo).
- run.py now honors PORT and RELOAD env vars (default 8000). We host on :8010 because
  another local app ("AAAFlow Studio") holds :8000. New launcher host-revelator.bat
  starts the server on :8010 and `cloudflared tunnel run revelator` in two windows.
- Still free: free Cloudflare account, free Universal SSL, laptop-hosted, local SQLite.
  Only paid item is the domain itself. CORS is allow_origins=["*"] and the SPA is served
  same-origin, so no origin config was needed. Google OAuth is NOT in the current build
  (no client id in the bundle); if re-added, add https://revelator.site to the OAuth
  client's Authorized JavaScript origins. FRONTEND_URL still defaults to localhost:5173
  (only affects password-reset link text; email is effectively off).

### 2026-07-04 - Local classifier + hybrid explain-only pipeline
- Trained a MobileNetV3 classifier on the specimen set (backend/train_classifier.py, on
  GPU). 19 code-level classes = the 15 forgery codes (TRACED/ERASURE/MODERN split by their
  method subfolders) + 6 "other" categories (charred/water/fold/embossing/typewriting/
  contact). 98.9% on the full set; 100% on the 98% of images it is confident about (>=0.85).
- Hybrid pipeline: analyze runs local_classifier first; confident -> Gemini gets a locked
  category + a short explain-only prompt (~150 words vs ~2850) = far fewer tokens and
  category-correct; uncertain (<0.85) -> full Gemini. Non-15 categories -> "other" ->
  Gemini explains. Config: USE_LOCAL_CLASSIFIER, LOCAL_CLASSIFIER_THRESHOLD (0.85).
  Model file: backend/app/data/specimen_classifier.pt (~17MB, gitignore it). Retrain:
  `cd backend && python train_classifier.py`. Verified end-to-end with a live Gemini call.
- Caveat: the classifier is memorized on the specimen set (overfit by design). On
  out-of-distribution real uploads it can be overconfident; the 0.85 gate + Gemini
  fallback mitigate but do not eliminate this. Keep a held-out split for thesis numbers.
- Also this session: registration auto-verify (REQUIRE_EMAIL_VERIFICATION=false) so signup
  no longer dead-ends on the broken verify link; AQ.-format Gemini keys accepted; single-
  origin hosting (backend serves the built frontend) + host.bat + free Cloudflare quick
  tunnel; superadmin moved to revenlatorforge@gmail.com.

### 2026-07-04 - First real specimen eval (partial, quota-limited)
- Ran evaluate_specimens.py on gemini-2.5-flash via the test account. Free-tier cap is
  20 requests/day/model, so it stopped after 19 images (4 folders). Partial signal, not a
  final number: 7/19 forged-vs-genuine, 1/9 category-hit. 19 scans saved to test history.
- Clear failure pattern (17 misses): heavy FALSE POSITIVES - 9/17 were genuine docs
  flagged "forged" at 0.85-1.00 confidence. `digital_scanned` over-fires on ordinary phone
  photos (3/3 genuine ADDITION), magnified close-ups get rejected as not_a_document, and
  charred docs fall into obliteration_ink/erasure. Confidence is not calibrated (0.95 on
  wrong answers) so the <0.80 critique never engages. Fix priorities: negative cues for
  digital_scanned, looser not_a_document for close-ups, and a genuine-bias / two-evidence
  threshold before "forged". A full run needs a paid key (removes the 20/day cap).

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
