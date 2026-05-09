# RAG (Retrieval-Augmented Generation) Improvement Plan

## The Concept

Instead of training Gemini, build a **reference database** of real forensic examples. When a new image comes in:
1. Find the most similar cases in the database
2. Show those cases to Gemini alongside the new image
3. Gemini reasons from real examples, not just general knowledge

This is how most production AI systems work — not by training from scratch, but by giving the model better context.

---

## What the Database Would Look Like

```json
{
  "examples": [
    {
      "id": "cp_001",
      "category": "digital_cut_paste",
      "image_path": "examples/cp_001.jpg",
      "indicators_found": [
        "digital halo at signature edge",
        "pixelation at 300% zoom",
        "shadow direction mismatch"
      ],
      "how_forgery_was_made": "Original signature extracted from another document, scaled to fit, pasted over blank line. Compression artifacts from JPEG re-encoding visible at boundary.",
      "what_to_look_for": "Check edges of placed element for fringing. Look for DPI mismatch between background and pasted element.",
      "confidence": "high",
      "document_type": "bank_check"
    },
    {
      "id": "clean_001",
      "category": "authentic",
      "image_path": "examples/clean_001.jpg",
      "indicators_found": [],
      "description": "Genuine bank check. Uniform ink distribution, no edge artifacts, consistent paper texture throughout.",
      "document_type": "bank_check"
    }
  ]
}
```

---

## How It Works in Practice

```
User uploads suspicious document
        ↓
Backend finds 2-3 similar examples from database (via image similarity)
        ↓
Sends to Gemini:

"Here are reference cases:

CASE 1 (digital_cut_paste): [image]
Indicators: halo at edges, pixelation, shadow mismatch
How it was made: signature pasted from another document...

CASE 2 (authentic): [image]
Indicators: none found
Description: uniform ink, no artifacts...

Now analyze this new image using these cases as reference: [user's image]"
        ↓
Gemini gives much more accurate analysis
```

---

## Implementation Plan

### Phase 1 — Build the Database (2-3 weeks)
- Collect 5-10 examples per category (190 total for 19 categories)
- Include authentic documents too (negative examples)
- Write detailed descriptions for each:
  - What indicators are present
  - How the forgery was made
  - What to look for
- Store in SQLite (already in project) or flat JSON files
- Suggested path: `backend/app/rag/examples/`

### Phase 2 — Image Similarity Search (1 week)
- Use **CLIP embeddings** to convert images to vectors
- When a new image comes in, compute its embedding
- Find the 2-3 most similar database entries (cosine similarity)
- Pull their descriptions + images for injection

**CLIP setup:**
```python
pip install open-clip-torch
import open_clip
model, _, preprocess = open_clip.create_model_and_transforms('ViT-B-32', pretrained='openai')
```

### Phase 3 — Inject into Gemini Prompt (2 days)
- Modify `backend/app/forgery/gemini_vision.py`
- Accept reference examples as additional context
- Format as few-shot examples before the main analysis prompt

**Prompt structure:**
```
[SYSTEM PROMPT — existing forensic taxonomy]

REFERENCE CASES FROM DATABASE:
Case 1: [image] — Category: digital_cut_paste
Indicators: ...
How made: ...

Case 2: [image] — Category: authentic
Description: ...

Now analyze the following document using the above cases as reference:
[USER'S IMAGE]
```

### Phase 4 — Feedback Loop (ongoing)
- Every confirmed scan result gets added to the database
- Users (or admins) can flag and label examples
- Database grows over time → accuracy improves continuously
- Eventually becomes a domain-specific training dataset

---

## Expected Accuracy Improvement

| Approach | Accuracy |
|---|---|
| Gemini Flash (current, no examples) | 85-90% |
| Gemini Flash + 2-3 reference examples | **92-96%** |
| Gemini Flash + perfect matched examples | **95-98%** |

Showing Gemini real cases for comparison makes a significant difference, especially for edge cases and similar categories (e.g. digital_cut_paste vs traced_projection).

---

## Token Cost Impact

Adding 2-3 reference images to each prompt increases cost:
- Current: ~9,000 tokens per scan (~$0.001)
- With 3 reference images: ~18,000-25,000 tokens (~$0.002-0.003)
- Still very cheap — roughly 2-3x cost for potentially 10%+ accuracy gain

Can optimize by:
- Only injecting examples when model confidence is low
- Using text-only reference descriptions (no images) to save tokens
- Caching frequently used examples

---

## Why This Is Strong for a Capstone

This is not just an API wrapper. You're implementing:

1. **Forensic Knowledge Base** — original domain research, manually curated
2. **RAG (Retrieval-Augmented Generation)** — real ML technique used in production at Google, OpenAI, etc.
3. **Image Similarity Search** — CLIP embeddings, cosine similarity
4. **Few-shot Learning** — in-context learning at inference time
5. **Feedback Loop** — database grows with confirmed scans

Thesis chapter title: *"Improving Forensic Classification Accuracy via Retrieval-Augmented Generation"*

---

## Biggest Challenge

Getting the **example images**. You need real labeled forensic documents for each category. Sources:
- Real documents from your testing so far (most realistic)
- Synthetic examples (intentionally create fake forgeries to demonstrate each type)
- Academic forensics datasets (some are publicly available):
  - CASIA Tampered Image Detection Dataset
  - Columbia Image Splicing Detection Dataset
  - DSO-1 dataset

---

## Files to Create/Modify

| File | Action |
|---|---|
| `backend/app/rag/database.json` | New — the example database |
| `backend/app/rag/examples/` | New — folder for example images |
| `backend/app/rag/retriever.py` | New — CLIP embedding + similarity search |
| `backend/app/forgery/gemini_vision.py` | Modify — inject reference examples into prompt |
| `backend/app/routes/analyze.py` | Modify — call retriever before Gemini |
| `backend/requirements.txt` | Add `open-clip-torch` |

---

## Status

- [ ] Phase 1: Build example database
- [ ] Phase 2: CLIP similarity search
- [ ] Phase 3: Gemini prompt injection
- [ ] Phase 4: Admin UI to add/label examples
- [ ] Phase 5: Feedback loop (confirmed scans auto-added)
