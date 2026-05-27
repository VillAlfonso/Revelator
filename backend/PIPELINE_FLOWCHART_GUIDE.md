# Revelator Optimization Pipeline - Flowchart Guide

This document is designed to be easily converted into a BPMN diagram or flowchart using tools like Lucidchart, Draw.io, or Miro.

---

## Quick Overview

```
START
  ↓ [user uploads image]
PREPROCESS → TRIAGE → DETAILED → CONFIDENCE GATE → RETURN
```

---

## Full Pipeline with All Decision Points

### Level 1: High-Level Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    START: Scan Request                       │
│           (user uploads image + optional context)            │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│              STAGE 0: PREPROCESS IMAGE                       │
│  • Input: Image file (any size, any format)                  │
│  • Process: Resize to 1024×1024px, quality 85%               │
│  • Output: Preprocessed image                                │
│  • Duration: <100ms | Cost: $0                               │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│              STAGE 1: TRIAGE CLASSIFY                        │
│  • Input: Preprocessed image                                 │
│  • Process: Quick classification with tiny prompt            │
│  • Model: gemini-2.5-flash (lightweight)                     │
│  • Output: top_3 category codes                              │
│  • Duration: ~2s | Cost: ~$0.00007                           │
│  • Example: ["digital_cut_paste", "traced_projection",       │
│             "no_forgery_detected"]                           │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│             STAGE 2: DETAILED ANALYSIS                       │
│  • Input: Preprocessed image + top_3 categories + context    │
│  • Process: Full forensic analysis (only for top-3)          │
│  • Cache: YES (90% discount if within 5 min)                 │
│  • Model: gemini-2.5-flash                                   │
│  • Output: {category, confidence, evidence, alternatives}    │
│  • Duration: ~3-5s | Cost: ~$0.0003                          │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│            STAGE 3: CONFIDENCE GATE (Decision)               │
│  "Is this result confident enough to return immediately?"    │
└──────────────┬──────────────────────────┬────────────────────┘
               ↓                          ↓
        CONFIDENCE                   CONFIDENCE
        >= 0.80?                      < 0.80?
               ↓ YES                       ↓ NO
         [CHEAP PATH]              [VERIFY PATH]
          (~$0.0003)                (~$0.0006+)
               ↓                          ↓
         RETURN RESULT          RUN CRITIQUE
            (END)               (verify classification)
                                       ↓
                                CRITIQUE DECISION
                                       ↓
                        ┌──────────────┴──────────────┐
                        ↓ AGREES                      ↓ DISAGREES
                  RETURN RESULT                  RUN ENSEMBLE
                    (~$0.0006)                    (~$0.001+)
                      (END)                            ↓
                                               ENSEMBLE VOTING
                                               (pick best result)
                                                      ↓
                                               RETURN RESULT
                                                    (END)
                                                     ↓
┌─────────────────────────────────────────────────────────────┐
│                      END: Return to User                     │
│   Scan result with category, confidence, evidence,           │
│   alternatives, and model tier used                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Detailed Process Boxes (for BPMN)

### Box 1: START
- **Type:** Start Event
- **Output:** Request object with image + user context
- **Next:** Preprocess

### Box 2: PREPROCESS IMAGE
- **Type:** Process
- **Input:** 
  - `image_data` (bytes)
  - `max_size` (int, default=1024)
- **Output:**
  - `preprocessed_image` (PIL Image)
  - `original_dimensions` (dict)
- **Function call:** `optimize.preprocess_image(image)`
- **Error handling:** Try/catch for invalid images
- **Next:** Triage Classify

### Box 3: TRIAGE CLASSIFY
- **Type:** Process
- **Input:**
  - `preprocessed_image` (PIL Image)
- **Output:**
  - `top_3` (list of category codes)
  - `reasoning` (str)
- **Function call:** `optimize.triage_classify(preprocessed_image)`
- **Duration:** ~2s
- **Cost:** ~$0.00007
- **Error handling:** If error, return all 19 categories as fallback
- **Next:** Detailed Classify

### Box 4: DETAILED CLASSIFY
- **Type:** Process
- **Input:**
  - `preprocessed_image` (PIL Image)
  - `top_3_categories` (list)
  - `document_type` (str, optional)
  - `suspicion_reason` (str, optional)
  - `area_of_concern` (str, optional)
  - `use_cache` (bool, default=True)
- **Output:**
  - `classification` (dict with all forensic analysis details)
  - `confidence` (float 0.0-1.0)
  - `category` (str)
- **Function call:** 
  ```python
  gemini_classify(preprocessed_image, 
                 document_type=..., 
                 use_cache=True)
  ```
- **Duration:** ~3-5s
- **Cost:** ~$0.0003
- **Caching:** Automatic (system prompt cached for 5 min)
- **Next:** Confidence Gate Decision

### Box 5: CONFIDENCE GATE (Decision Diamond)
- **Type:** Decision
- **Condition:** `confidence >= 0.80`
- **True branch:** → CHEAP PATH (return immediately)
- **False branch:** → VERIFY PATH (run critique)
- **Input:** `confidence` (float)
- **Output:** Decision branch

#### Branch A: CHEAP PATH (Confidence >= 0.80)
- **Type:** Path
- **Cost:** ~$0.0003
- **Process:** None (return immediately)
- **Next:** END

#### Branch B: VERIFY PATH (Confidence < 0.80)
- **Type:** Path
- **Cost:** ~$0.0006 (if critique agrees) or ~$0.001+ (if ensemble)
- **Process:** Run critique
- **Next:** Critique Decision

### Box 6: RUN CRITIQUE
- **Type:** Process
- **Input:**
  - `preprocessed_image` (PIL Image)
  - `original_classification` (dict)
  - `original_confidence` (float)
- **Output:**
  - `critique_result` (dict)
  - `agrees` (bool)
  - `alternative_category` (str, optional)
  - `alternative_confidence` (float, optional)
- **Function call:** `optimize._run_critique(client, image, result)`
- **Duration:** ~2-3s
- **Cost:** ~$0.0003
- **Next:** Critique Decision

### Box 7: CRITIQUE DECISION (Decision Diamond)
- **Type:** Decision
- **Condition:** `critique_result["agrees"]`
- **True branch:** → Return original result
- **False branch:** → Run ensemble voting
- **Next:** Either END or ENSEMBLE

### Box 8: RUN ENSEMBLE VOTING
- **Type:** Process
- **Input:**
  - `preprocessed_image` (PIL Image)
  - `original_result` (dict)
  - `critique_result` (dict)
- **Output:**
  - `final_result` (dict with best classification)
- **Function call:** `optimize._run_ensemble_vote(client, image, ...)`
- **Duration:** ~5-10s (may run multiple calls)
- **Cost:** ~$0.0006 (additional)
- **Next:** END

### Box 9: END
- **Type:** End Event
- **Input:** Final classification result
- **Output:** Return JSON to frontend
- **HTTP Status:** 200 OK
- **Response contains:**
  - `scan_id`
  - `verdict` (forged/suspicious/no_forgery_detected)
  - `confidence_score`
  - `detected_category`
  - `category_explanation`
  - `evidence` (list)
  - `alternatives` (list)
  - `certainty_level`
  - `reasoning_steps`
  - `model_tier_used`

---

## Data Flow Diagram

```
INPUT
  ↓
  ├─ image_file (bytes)
  ├─ document_type (str)
  ├─ suspicion_reason (str)
  ├─ area_of_concern (str)
  └─ [other context fields]
  ↓
PREPROCESS
  ↓
  ├─ original_dimensions: {width: 4032, height: 3024}
  └─ preprocessed_image: PIL Image (1024×1024)
  ↓
TRIAGE
  ↓
  ├─ top_3: ["digital_cut_paste", "traced_projection", "no_forgery_detected"]
  └─ reasoning: "Clear halo artifact suggests digital cut-paste..."
  ↓
DETAILED
  ↓
  ├─ category: "digital_cut_paste"
  ├─ confidence: 0.92
  ├─ evidence: ["halo at edge", "pixelation visible"]
  ├─ anomaly_location: "top-right signature area"
  └─ alternatives: [{category: "...", reasoning: "..."}, ...]
  ↓
GATE CHECK
  ↓ confidence >= 0.80?
  ├─ YES → return to user
  └─ NO → CRITIQUE
       ↓
       ├─ agrees: true/false
       └─ (if false) alternative_category: "..."
            ↓
            ├─ YES → return original
            └─ NO → ENSEMBLE
                 ↓
                 └─ final_result: {...}
  ↓
OUTPUT to user
```

---

## SQL/Database State (Optional)

```
Before:
  Scan.image_width = 4032
  Scan.image_height = 3024

After Preprocess:
  Scan.image_width = 1024  (actual saved size)
  Scan.image_height = 683   (actual saved size)

Response includes:
  {
    "original_image_dimensions": {
      "width": 4032,
      "height": 3024
    }
  }
```

---

## Configuration Matrix

For each decision point / threshold, here's what can be tuned:

| Parameter | Default | Location | Impact |
|-----------|---------|----------|--------|
| `max_image_size` | 1024 | `optimize.preprocess_image()` | Token savings |
| `high_confidence_threshold` | 0.80 | `confidence_gated_analyze()` | % taking cheap path |
| `medium_confidence_threshold` | 0.50 | `confidence_gated_analyze()` | When to run critique |
| `cache_ttl` | 300s (5 min) | `prompt_cache.py` | Active session optimization |
| `triage_model` | gemini-2.5-flash | `triage_classify()` | Speed/accuracy tradeoff |
| `detailed_model` | gemini-2.5-flash | `gemini_classify()` | Default model |

---

## BPMN Symbols

When converting to BPMN:

| Box Type | BPMN Symbol | Color |
|----------|-----------|-------|
| START / END | Circle | Green / Red |
| Process | Rectangle | Blue |
| Decision | Diamond | Yellow |
| Subprocess | Rectangle (rounded) | Light Blue |
| Parallel Gateway | Diamond (Y shape) | Orange |

---

## Pool & Lane Diagram (Swimlanes)

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                              │
│  User uploads image                                         │
│  ↓                                                           │
│  POST /api/analyze                                          │
└─────────────────────────────────────────────────────────────┘
                       ↓ HTTP Request
┌─────────────────────────────────────────────────────────────┐
│                   BACKEND: OPTIMIZE PIPELINE                 │
│  Lane 1: Image Processing                                   │
│  ├─ Preprocess                                              │
│  └─ Validation                                              │
│                                                              │
│  Lane 2: Classification (Gemini)                            │
│  ├─ Triage                                                  │
│  ├─ Detailed (cached)                                       │
│  └─ Critique (on demand)                                    │
│                                                              │
│  Lane 3: Database                                           │
│  └─ Save Scan result                                        │
└─────────────────────────────────────────────────────────────┘
                       ↓ HTTP Response (JSON)
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                              │
│  Display result to user                                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Parallel Processing (if implemented in future)

```
Preprocess can run in parallel with:
  • User context extraction
  • Initial validation checks

Triage and Detailed could run in parallel:
  • Triage (quick, low cost)
  • Detailed (full analysis)
  Then take max(confidence) result

Critique and Ensemble could run in parallel:
  • Critique 1 (verify original)
  • Critique 2 (alternative perspective)
  • Vote on result
```

---

## Thresholds & Scoring

### Confidence Score Scale

```
0.90-1.00   ████████████████  "High - Multiple unambiguous signs"
0.70-0.89   ██████████        "Medium - Clear signs but ambiguity"
0.50-0.69   ███████           "Low - Suspicious but not definitive"
0.30-0.49   ████              "Very Low - Weak signal"
0.00-0.29   ██                "No evidence"
```

### Verdict Mapping (from confidence)

```
Confidence >= 0.70 AND category is forgery type
  → verdict = "forged"

0.50 <= Confidence < 0.70 AND category is forgery type
  → verdict = "suspicious"

Confidence < 0.50 OR category is no_forgery_detected
  → verdict = "no_forgery_detected"

Category is not_a_document
  → verdict = "not_a_document"
```

---

## Error Handling Paths

### If Preprocess Fails
```
Exception during image read/convert
  ↓
400 Bad Request: "Invalid image: [error message]"
→ END (error)
```

### If API Unavailable
```
Gemini Vision API rate-limited or offline
  ↓
Try fallback models (pro → flash → flash-lite)
  ↓
Still fails? 
  ↓
503 Service Unavailable
→ END (error)
```

### If Triage Fails
```
Fallback: use all 19 categories (no narrowing)
  ↓
Continue to detailed analysis
```

### If Critique Fails
```
Exception during critique
  ↓
Return original result (skip critique)
  ↓
Proceed to END
```

---

## Testing Paths

### Happy Path (High Confidence)
```
Preprocess → Triage (successful) → Detailed (0.92 confidence)
  ↓ Gate: 0.92 >= 0.80? YES
  ↓ Return immediately
→ END (200 OK)
```

### Medium Path (Critique Needed)
```
Preprocess → Triage → Detailed (0.65 confidence)
  ↓ Gate: 0.65 >= 0.80? NO
  ↓ Run Critique
  ↓ Critique agrees? YES
  ↓ Return original
→ END (200 OK)
```

### Full Path (Ensemble)
```
Preprocess → Triage → Detailed (0.55 confidence)
  ↓ Gate: 0.55 >= 0.80? NO
  ↓ Run Critique
  ↓ Critique agrees? NO
  ↓ Run Ensemble
  ↓ Get best result
→ END (200 OK)
```

---

## Metrics to Collect (for monitoring)

```
Per Scan:
  • preprocess_time_ms
  • triage_cost
  • detailed_cost
  • critique_cost (if run)
  • ensemble_cost (if run)
  • total_tokens
  • total_cost
  • confidence_level
  • path_taken (cheap/medium/ensemble)
  • accuracy_if_known

Aggregate:
  • % scans taking each path
  • Average cost per scan
  • Average tokens per scan
  • Cache hit rate
  • Accuracy by path
```

---

## Pseudo-code

```
function analyze_document(image, context):
    # STAGE 0
    preprocessed = preprocess_image(image)
    
    # STAGE 1
    triage = triage_classify(preprocessed)
    top_3 = triage.top_3
    
    # STAGE 2
    result = gemini_classify(preprocessed, top_3, context, use_cache=TRUE)
    confidence = result.confidence
    
    # STAGE 3
    if confidence >= 0.80:
        return result  # Cheap path
    endif
    
    if confidence >= 0.50:
        critique = run_critique(preprocessed, result)
        if critique.agrees:
            return result  # Medium path
        endif
    endif
    
    # Low confidence or critique disagrees
    ensemble = run_ensemble(preprocessed, result, critique)
    return ensemble  # Full path


function run_critique(image, result):
    critique = call_gemini_with_critique_prompt(image, result)
    return critique


function run_ensemble(image, original, critique):
    if critique.agrees:
        return original
    else:
        alternative_result = call_gemini_for_alternative(image, critique.alternative_category)
        return pick_best(original, alternative_result)
    endif
```

---

## Conversion Checklist

When converting to Lucidchart / Draw.io / Visio:

- [ ] Add START/END circles
- [ ] Add 4 main process boxes (Preprocess, Triage, Detailed, Gate)
- [ ] Add decision diamonds for Gate and Critique decisions
- [ ] Add subprocess boxes for Critique and Ensemble
- [ ] Label all edges with conditions (confidence >= 0.80, etc.)
- [ ] Add cost/timing annotations
- [ ] Color-code by stage (blue for processing, yellow for decisions)
- [ ] Add data flow arrows showing inputs/outputs
- [ ] Optional: Add swimlanes for Frontend/Backend/Database
- [ ] Optional: Add error handling paths
- [ ] Add legend for symbols
- [ ] Add decision table matrix for thresholds
