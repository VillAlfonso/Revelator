# Capstone Documentation — Reference Sheet

Private prep notes (gitignored). The user is going to write Chapters 1-3
and will send the template. This doc captures the project facts I'll
need on hand when those chapters get drafted.

---

## Project at a glance

- **Name:** Revelator (was ForgeGuard)
- **Institution:** LSPU (Laguna State Polytechnic University, PH)
- **Goal:** AI-assisted document forgery detection — screening tool that
  complements human forensic examination
- **Vision:** Single "Scan Document" button → auto-detect which forgery type
  (if any) among 16 categories → return verdict + forensic explanation
- **Capstone scope:** Phase 1 allows category selection (MVP); auto-detection
  (Phase 2) deferred until full dataset coverage
- **Defense framing:** Self-trained models, not cloud-API wrappers.
  Honest about limitations: "absence of evidence ≠ proof of authenticity"

## What it actually does (process)

1. User uploads document image (web/mobile)
2. **Document gate** — vision LLM (local Llama 3.2 11B Vision via Ollama,
   or Groq cloud) checks if it's actually a document. If not, returns
   conversational rejection ("This is a screenshot of a video game…").
   Skips quota and DB write.
3. **Detection** — YOLOv8 model for the chosen category (or all 16 in
   "auto-detect"). Local weights have priority; Roboflow API is fallback.
4. **ELA computation** — Error Level Analysis re-saves at known JPEG
   quality, amplifies pixel-wise difference. Highlights regions with
   inconsistent compression history.
5. **Aggregation** — verdict assigned: forged / suspicious /
   no_forgery_detected / not_a_document.
6. **LLM explanation** (pro/premium tier) — vision LLM receives a
   side-by-side `[annotated original | ELA map]` panel + structured
   prompt, returns a forensic-examiner-style explanation citing both
   detection bboxes and ELA hotspots.
7. **Persistence** — scan saved with image, annotations, verdict, LLM
   text. Visible in user history.

## Tech stack

| Layer | What |
|---|---|
| Backend | FastAPI, SQLAlchemy, SQLite (production-ready: Postgres) |
| Auth | JWT-based, refresh tokens |
| Detection | YOLOv8 nano, ultralytics 8.1.0 |
| Vision LLM (local) | Ollama + Llama 3.2 11B Vision |
| Vision LLM (cloud) | Groq + Llama 4 Scout |
| Forensics helper | ELA — Error Level Analysis (Krawetz 2007 / FotoForensics method) |
| Frontend | React + Vite, plain CSS |
| Mobile | Capacitor (Android-first) |
| Payments | Stripe (mostly decorative for capstone) |
| Data prep | synthesize.py (with cross-source, scale-rotate, color-match, multi-region, negatives, source-split flags) |
| Sources | Hugging Face datasets — CORD-v2, FUNSD; user's own scans; Roboflow handcrafted set |
| Training | Google Colab T4 (free) |

## The 16 forgery categories

| Category | Plain meaning | Tier |
|---|---|---|
| traced_carbon | Signature traced via carbon paper | 3 |
| traced_indentation | Signature traced from page-below indentation | 3 |
| traced_projection | Signature traced via projection / lightbox | 3 |
| addition_insertion | New characters squeezed into existing text | 1 |
| addition_interlineation | New text added between existing lines | 1 |
| erasure_chemical | Ink dissolved with chemicals | 2 |
| erasure_mechanical | Ink physically erased | 2 |
| digital_cut_paste | Photoshop-style splice | 1 (✓ training underway) |
| digital_desktop | Fully fabricated in Word/Canva/Photoshop | 1 |
| digital_scanned | Forgery hidden via scan/photocopy generation loss | 2 |
| obliteration_ink | Crossed out with ink/marker | 2 |
| obliteration_whiteout | Covered with correction fluid | 1 |
| obliteration_pigment | Covered with paint/opaque marker | 2 |
| sympathetic_indented | Indentation impressions revealed under raking light | 3 |
| sympathetic_special | UV-fluorescent / invisible ink | 3 |
| currency_analysis | Counterfeit banknotes vs genuine | 3 |

(Tier 1 = easiest to dataset; tier 3 = needs special equipment)

## Architecture diagram-worthy facts

For a System Architecture / Conceptual Framework figure:

```
┌─────────────────────┐        ┌─────────────────────┐
│  React/Capacitor UI │ HTTPS  │   FastAPI Backend   │
│  (web + Android)    │◄──────►│                     │
└─────────────────────┘        └──────┬──────┬──────┘
                                      │      │
                  ┌───────────────────┘      │
                  │                          │
                  ▼                          ▼
          ┌──────────────┐         ┌────────────────┐
          │ Document Gate│         │ Detection Path │
          │ (Vision LLM) │         │  (YOLOv8 +     │
          └──────────────┘         │   Roboflow     │
                                   │   fallback)    │
                                   └───────┬────────┘
                                           │
                                  ┌────────▼────────┐
                                  │ ELA computation │
                                  └────────┬────────┘
                                           │
                                  ┌────────▼─────────┐
                                  │  Vision LLM      │
                                  │  Explainer       │
                                  │  (Ollama / Groq) │
                                  └────────┬─────────┘
                                           │
                                  ┌────────▼─────────┐
                                  │  SQLite DB +     │
                                  │  Image storage   │
                                  └──────────────────┘
```

## What chapters typically look like in PH/LSPU capstone format

### Chapter 1 — Introduction

Subsections that almost always appear:
- **Background of the Study** — context of document forgery in PH, motivation for tool
- **Theoretical Framework** — pull from forensic document examination science (Hilton, Osborn) + AI/computer-vision lineage (YOLO papers, ELA Krawetz 2007)
- **Conceptual Framework** — input/process/output (IPO) diagram or similar
- **Statement of the Problem** — main + sub-questions
- **Hypothesis** (sometimes) — model achieves X mAP, document gate rejects Y% of non-documents
- **Significance of the Study** — beneficiaries: forensic examiners, legal professionals, ordinary citizens, researchers
- **Scope and Delimitation** — 16 categories declared but defended subset, screening tool not replacement, PH-context documents
- **Definition of Terms** — forgery, ELA, YOLO, mAP, vision LLM, etc.

### Chapter 2 — Review of Related Literature (RRL)

- **Foreign literature/studies** — YOLO architecture, ELA technique, MVSS-Net,
  ManTra-Net, document-forgery detection benchmarks (CASIA, COVERAGE)
- **Local literature/studies** — Filipino research on forgery, BSP currency
  features, NBI/PNP forensics if any published, related capstones at LSPU/UPLB/etc.
- **Synthesis / gap analysis** — what nobody else has done that Revelator fills

### Chapter 3 — Methodology

Subsections that almost always appear:
- **Research Design** — descriptive-developmental / agile / iterative
- **Subjects of the Study** — testers / evaluators / panel
- **Research Instrument** — evaluation rubric (e.g. ISO 25010 software quality)
- **Data Gathering Procedures** — dataset sourcing (real + synthesized), test
  protocol
- **Statistical Treatment** — usually ISO 25010 weighted mean per criterion
- **Software Development Methodology** — Agile / Scrum / Spiral / RAD;
  iterative cycles aligning with the trajectory above
- **System Architecture** (diagram)
- **Use Case Diagram** (UML)
- **BPMN / Activity Diagrams** for flows like "user scans document",
  "admin reviews scan history"
- **ERD** (Entity-Relationship Diagram) for the database
- **DFD** (Data Flow Diagram) — context level + level-1 explosion
- **Hardware/Software Requirements**
- **System Testing Plan** — unit, integration, UAT

## Diagrams to draft when chapters get written

Probably needed:

1. **System Architecture** (one figure, clean version of the ASCII above)
2. **Use Case Diagram** — actors: User, Admin, System; use cases: register,
   login, scan document, view history, view explanation, manage subscription
3. **BPMN — Document Scan Workflow** — captures the gate → detection → ELA
   → LLM → persistence flow
4. **Activity Diagram — Forgery Detection Decision Path** — input → gate
   pass/fail → category routing → verdict assignment
5. **Class / ER Diagram** — User, Scan, Subscription tables (already exist
   in `backend/app/models.py`)
6. **DFD Level 0** — context: external user ↔ Revelator System ↔ Stripe API ↔
   LLM service
7. **DFD Level 1** — internal data stores: User DB, Scan DB, Image storage,
   Trained models
8. **Sequence Diagram — Single Scan** — user → upload → backend → gate →
   detector → ELA → LLM → DB → response
9. **Gantt Chart** — capstone timeline (sourcing dataset → training tier 1
   categories → tier 2 → tier 3 → polish → defense)

Tools: Mermaid (renders in markdown, GitHub-friendly), draw.io, Lucidchart,
PlantUML. Mermaid is the lowest-friction for the user since it's just text
and renders without external software.

## Things to remember when chapters arrive

- The **abstract** should mention: 16-category forensic scope, YOLOv8
  detector, ELA cross-reference, vision-LLM explainer, document gate,
  PH-context dataset.
- Numbers from completed training runs go in chapter 4 (Results), not 3.
  Don't write them prematurely.
- ISO 25010 evaluation framework (functionality, reliability, usability,
  efficiency, maintainability, portability, security, compatibility) is a
  standard rubric panel members will expect.
- **Honest scoping**: Define which categories are "in scope" and which are
  "future work" so the panel doesn't grade against unbuilt categories.
- Cite original papers properly:
  - YOLOv8 — Ultralytics (no peer-reviewed YOLOv8 paper, cite repo + YOLOv1
    Redmon et al. 2016)
  - ELA — Krawetz, "A Picture's Worth..." (2007)
  - Llama 3 / Llama 4 — Meta technical reports
  - Synthesize-based forgery training — MVSS-Net (Chen et al. 2021),
    ManTra-Net (Wu, AbdAlmageed, Natarajan 2019)

## Indentation synthesis implementation (IN PROGRESS)

**Dataset generation script:** `models/traced_indentation/synthesize_indentation.py`

**Execution:**
```bash
python synthesize_indentation.py \
  --real-dir /path/to/24/real/samples \
  --clean-dir /path/to/clean/documents \
  --output-dir ./synthetic \
  --count 150 \
  --negatives 30
```

**What it does:**
1. Analyzes 24 real indentation samples to extract visual characteristics
2. For each of 49 clean documents:
   - Creates 150 synthetic indentation variants
   - Each variant adds: traced signature marks + groove/shadow artifacts (visible under raking light)
   - Applies augmentations: brightness, blur, rotation, JPEG compression (realistic photo conditions)
3. Copies 30 clean documents as negatives (empty YOLO labels, teaches model not to flag clean docs)
4. Organizes into YOLO splits: 70% train, 20% valid, 10% test

**Expected output:**
- ~7,350 synthetic indentation forgeries
- ~30 clean document negatives
- ~7,380 total images
- Ratio: ~99% forged, ~0.4% clean (we'll augment clean count later if needed)
- Ready for YOLOv8 training

**Status:** Running in background (May 2, 2026)

**Training infrastructure:**
- `models/traced_indentation/train_indentation.py` — Train YOLOv8 on synthetic dataset
- `models/phase2_auto_detect.py` — Test Phase 2 single-button auto-detection
- Run after synthesis completes:
  ```bash
  cd models/traced_indentation
  python train_indentation.py --epochs 50 --imgsz 640 --batch 16
  # Once done, test Phase 2:
  cd ..
  python phase2_auto_detect.py --image <test_image.jpg> \
                               --cut-paste-model digital_cut_paste/weights/best.pt \
                               --indentation-model traced_indentation/weights/best.pt
  ```

---

## Capstone phasing: MVP → Phase 2 proof-of-concept

**Phase 1 (MVP / Current Capstone):**
- User selects category (dropdown), uploads image
- System runs that category's YOLO model + ELA + LLM explanation
- Validates the pipeline end-to-end with Tier 1 categories (cut-paste, etc.)

**Phase 2 (Proof-of-concept / Mid-capstone):**
- After indentation model is trained, test the **single "Scan Document" button**
- System runs *all trained models in parallel* (e.g., cut-paste detector + indentation detector)
- Logic:
  - If cut-paste fires: return "digital_cut_paste"
  - If indentation fires: return "traced_indentation"
  - If neither fire: return "no_forgery_detected"
  - If both fire: return highest-confidence category
- **Test with mixed real documents**: some cut-paste, some indentation, some clean
- Demonstrates the auto-detection vision works with 2 categories

**Phase 2B (Future / Post-capstone):**
- Scale to all 16 categories as datasets improve
- More sophisticated routing (ensemble classifier vs. parallel detectors)
- This is where the full "single button" vision lives

**Why this progression shows well in the thesis:**
- Capstone: "Demonstrated multi-category detection system; achieved Phase 2 proof-of-concept with 2 categories"
- Shows the architecture is scalable; future work adds more categories
- Real end-to-end test (not just individual models in isolation)

## Data availability per category & academic framing

**Key insight:** This is NOT a failure—it's a realistic capstone story. You're demonstrating methodology under real-world constraints, not with unlimited resources.

### Strong categories (well-resourced)
- **digital_cut_paste** (6,500+ samples): ~85–92% accuracy expected
  - Lead with this in results; it's your strength
  - Show precision/recall curves, confusion matrix
- **Other Tier 1** (erasure_chemical, digital_scanned, obliteration_whiteout): 
  - Sourced from CORD, FUNSD, + synthesis → reasonable data
  - Target ~75–85% accuracy

### Data-limited categories (synthesis-augmented strategy)
- **traced_indentation** (24 real samples → 7,380 synthesized + augmented):
  - **Real data origin**: 24 authenticated traced indentation samples from Roboflow project
  - **Synthesis approach** (IMPLEMENTED):
    - **What is traced indentation?** Signature/text traced from beneath (leaving grooves) vs. written normally
      - Two components: (1) traced ink marks, (2) indentation grooves/shadows visible under raking light
      - Roboflow labels marked the signatures; synthesis adds the groove artifacts
    - **Custom synthesizer** (`synthesize_indentation.py`):
      - Analyzes 24 real samples to extract visual characteristics (shadow patterns, groove depth)
      - Adds synthetic indentation marks to 49 clean documents:
        - Simulated traced signature lines with pen-pressure waviness
        - Groove/shadow artifacts (darkened edges, depth cues, subtle blur to simulate embossing)
        - Realistic augmentations: brightness jitter, Gaussian blur, JPEG recompression, 2° rotation
      - Generates 150 variants per clean document = ~7,350 synthetic forgeries
      - Adds 30 clean documents as negatives (empty labels) to suppress false positives
      - Output: 7,380 images split 70/20/10 train/valid/test, YOLO-formatted
  - **Expected accuracy**: 70–80% on real held-out test set (4–5 real samples reserved for evaluation)
  - **Thesis framing (Chapter 3)**:
    - "Traced indentation dataset consisted of 24 real samples + 49 clean documents"
    - "Custom synthesis pipeline generated 150 variants per clean document, following MVSS-Net methodology"
    - "Added groove/indentation artifacts simulating pressure-mark shadows under raking light"
    - "7,350 synthetic forgeries + 30 clean negatives = 7,380 training images (99.6% synthetic, 0.4% clean)"
    - "Data composition limited by forensic dataset availability; production deployment would benefit from 200+ real indentation samples to reduce synthesis dependency"
  - **This demonstrates**: methodology under realistic data constraints, honest assessment of limitations
  - **Future Work**: "Collect 200+ real indentation samples from forensic labs; reduce synthesis ratio; improve accuracy to 85%+"

- **Tier 3 categories** (currency, sympathetic_special, etc.):
  - Mark as "future work" in scope if not trained
  - Panel expects honest scoping; don't claim what you didn't build

### Implementation strategy for traced_indentation synthesis

**Phase 1 — Characterize the 24 real samples:**
- Analyze visual features: shadow patterns, groove depth appearance, edge softness
- Extract metadata: lighting angle, paper type, pen pressure signature
- Build a "style profile" of real indentation artifacts

**Phase 2 — Build indentation-specific synthesizer:**
- Unlike cut-paste (which physically copies regions), indentation is *additive*
- Approach: overlay synthetic indentation marks onto clean documents
- Synthetic marks should match the extracted visual profile:
  - Shadow gradients (varying opacity along groove)
  - Texture patterns (micro-roughness under light)
  - Depth cues (soft edges, light/dark gradient)
- Reference: MVSS-Net uses conditional generation; adapt that pattern for indentation

**Phase 3 — Aggressive augmentation (NOT re-synthesis):**
- Per real sample + clean doc, generate 300–500 variants:
  - Lighting angle rotation (simulate ESDA + raking light variations)
  - Scale/position randomization
  - Blur/compression (simulate photo capture)
  - Background variation (different papers, ages)
  - Brightness/contrast jitter
- **Don't re-synthesize synthetic images** — augment them directly instead
  - Real → Synthetic Gen 1: high quality
  - Gen 1 + transforms (rotate, blur, etc.): more diversity without quality loss
- Target: 24 real + 7,000–10,000 first-generation synthetic + augmented variants
- Split: 70% train, 20% valid, 10% test (hold out 4–5 real samples for actual test)

**Phase 4 — Training & Phase 2 test:**
- Train indentation YOLOv8 model on synthetic dataset (7,350 forged + 30 clean)
- Monitor validation loss/accuracy on val split
- **Phase 2 POC - Single Button Auto-Detection Test**:
  - Once indentation model trained, deploy to backend
  - Enable the single "Scan Document" button in UI
  - Backend runs both detectors in parallel:
    ```python
    cut_paste_result = cut_paste_model.predict(image)
    indentation_result = indentation_model.predict(image)
    
    if cut_paste_result.conf > threshold:
      return "digital_cut_paste"
    elif indentation_result.conf > threshold:
      return "traced_indentation"
    else:
      return "no_forgery_detected"
    ```
  - **Test set**: Mix real documents (10 cut-paste, 10 indentation, 5 clean)
  - System should correctly classify each
  - This validates the auto-detection architecture before scaling to 16 categories

**Phase 5 — Results & validation:**
- Report per-model accuracy:
  - Cut-paste: mAP50 on test set + confidence intervals
  - Indentation: mAP50 on held-out real test set (4-5 samples)
- Report Phase 2 mixed-test results: "Of 25 mixed documents, correctly auto-identified X as cut-paste, Y as indentation, Z as clean"
- **Key metric**: Hold-out real test accuracy (not synthesis validation accuracy)
- Demonstrate scalability: "This POC with 2 categories validates the architecture for expanding to 16 categories"

### How to frame in Chapters 3 & 4

**In Chapter 3 (Methodology) — Section 3.1: Data Gathering**

Create a table showing dataset composition:

| Category | Real Samples | Synthesis Method | Synthetic Output | Negatives | Total | Ratio |
|----------|-------------|------------------|------------------|-----------|-------|-------|
| digital_cut_paste | 6,500 (mostly synthetic) | Roboflow trained | 6,023 | 500 clean | 6,523 | 92:8 |
| traced_indentation | 24 real | Custom synthesizer | 7,350 | 30 clean | 7,380 | 99:0.4 |

**In Chapter 3 — Section 3.2: Synthesis Pipeline**

For traced_indentation, document:
- **Input**: 24 authenticated samples + 49 clean documents from CORD/FUNSD
- **Process**: 
  1. Extract indentation characteristics (shadow patterns, groove texture)
  2. Generate synthetic marks: traced lines + shadow/groove artifacts
  3. Apply realistic augmentations (brightness, blur, rotation, JPEG)
  4. Create 150 variants per clean document
- **Output**: 7,350 forged + 30 clean = 7,380 YOLO-formatted images
- **Rationale**: Synthesis extends 24 real samples; follows MVSS-Net/ManTra-Net methodology (standard in document forgery research)

**In Chapter 4 (Results) — Section 4.1: Model Performance**

Present results per category with transparency:

**Digital Cut-Paste (Well-Resourced):**
- Training set: 4,537 synthetic + 349 clean = 4,886 images
- Validation accuracy: [X]% mAP50
- Test accuracy on real hold-out: [Y]% mAP50
- Conclusion: High confidence for production screening

**Traced Indentation (Synthesis-Limited):**
- Training set: 7,350 synthetic (from 24 real) + 30 clean = 7,380 images
- Validation accuracy: [X]% mAP50
- Test accuracy on 4 held-out real samples: [Y]%
- **Critical transparency statement**: 
  - "Model trained on 99.6% synthetic data, validated on hold-out real samples"
  - "Real-world accuracy may vary; synthesis quality constrained by 24 real sample base"
  - "Recommend 200+ real indentation samples for production deployment"
- Conclusion: Suitable for forensic screening; human review recommended for final verdict

**Phase 2 POC (Auto-Detection):**
- Tested single-button detection with mixed real documents (cut-paste + indentation + clean)
- Accuracy on mixed set: [X]% (correctly identified which type each document was)
- Demonstrates scalable architecture for expanding to 16 categories

### Why this works academically
✓ Shows you understand real ML constraints  
✓ Honest about limitations (credibility)  
✓ Proposes solutions for production deployment  
✓ Demonstrates research methodology, not magic  
✓ Panel respects "limited data, methodical approach" over "unlimited data, claimed 99% accuracy"  

## Things NOT to do prematurely

- Don't write chapters before user sends template (format conventions
  vary by institution).
- Don't generate Chapter 4/5 (Results, Conclusion) until training is done
  and numbers are real. Placeholder numbers in a draft are dangerous —
  they get accidentally accepted.
- Don't generate diagrams in vector formats — produce them as Mermaid text
  inside the chapter so the user can edit and re-render.
- Don't claim 100% accuracy on any category. Real ML never gets there;
  panels see through it.
