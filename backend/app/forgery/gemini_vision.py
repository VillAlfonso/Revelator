"""
Gemini Vision - primary forensic classifier.

Reads the document image and returns a structured JSON verdict against the
19-category taxonomy. Output is parsed into a dict that the analyze route
saves to the Scan row.

Design choices to minimize hallucinations:
  - Chain-of-thought reasoning (model must show its work before classifying)
  - Negative constraints (explicit IGNORE list to avoid flagging benign issues)
  - Anomaly location grounding (forced to point to a specific region when forged)
  - Optional user context (focus area, source, suspicion) that narrows the search
"""

from __future__ import annotations

import io
import json
import re
from typing import Optional, Dict, Any

from PIL import Image

from ..config import GEMINI_API_KEY, GEMINI_VISION_MODEL

# Fallback chain: best quality first, lite last.
# If GEMINI_VISION_MODEL is set in .env, only that model is used (no fallback).
# Otherwise, cascade through this chain on rate limit errors.
_FALLBACK_CHAIN = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"]

def _model_chain() -> list[str]:
    """Return ordered list of models to try. If a model is explicitly set, use only that."""
    if GEMINI_VISION_MODEL:
        return [GEMINI_VISION_MODEL]  # Use explicitly configured model, no fallback
    return list(_FALLBACK_CHAIN)  # Otherwise, cascade through the default chain


def _is_rate_limited(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in ("429", "quota", "rate_limit", "rateerror", "resource_exhausted", "exhausted"))


# ── Category taxonomy ──────────────────────────────────────────────────────
CATEGORIES = [
    # Traced
    ("traced_carbon",            "Traced - Carbon Transfer"),
    ("traced_indentation",       "Traced - Indentation / Canal Light"),
    ("traced_projection",        "Traced - Projection Process"),
    # Alteration
    ("addition_insertion",       "Alteration - Addition: Insertion"),
    ("addition_interlineation",  "Alteration - Addition: Interlineation"),
    ("erasure_chemical",         "Alteration - Erasure: Chemical"),
    ("erasure_mechanical",       "Alteration - Erasure: Mechanical"),
    # Digital
    ("digital_cut_paste",        "Cut and Paste Forgery"),
    ("digital_desktop",          "Digital - Desktop Publishing"),
    ("digital_scanned",          "Digital - Scanned Document"),
    # Obliteration
    ("obliteration_ink",         "Obliteration - Ink Stroke"),
    ("obliteration_whiteout",    "Obliteration - White Out"),
    # Sympathetic Ink
    ("sympathetic_indented",     "Sympathetic Ink - Indented Writing"),
    ("sympathetic_special",      "Sympathetic Ink - Special Ink"),
    # Currency
    ("currency_analysis",        "Currency Forgery"),
    # Fallbacks
    ("no_forgery_detected",      "No Forgery Detected"),
    ("not_a_document",           "Not a Document"),
    ("other",                    "Other Forgery"),
]

CATEGORY_CODES = [c[0] for c in CATEGORIES]
CATEGORY_LABELS = dict(CATEGORIES)


SYSTEM_PROMPT = """You are a forensic document examiner. Classify the image into EXACTLY ONE of the 18 categories below. Reason step by step before answering, and only flag a forgery when you can point to specific visible evidence.

CATEGORIES (use the code on the left in your JSON):

═══════════════════════════════════════════════════════════════════════════
CRITICAL BRANCHING RULE - FIRST DECISION:
  Is the text/signature HAND-DRAWN INK ON PAPER, or SOFTWARE-GENERATED?
  - If HAND-DRAWN INK: Look at traced_carbon, traced_indentation, traced_projection
  - If SOFTWARE-GENERATED: Look at digital_desktop, digital_cut_paste, digital_scanned

  Key test: Can you see PHYSICAL PEN MARKS (ink strokes, grooves, tremor, hesitation, carbon residue)?
    YES → traced category
    NO (perfect font consistency, digital-looking letters) → digital category
═══════════════════════════════════════════════════════════════════════════

Traced:
  traced_carbon            - Carbon-paper transfer: forger places carbon paper under a genuine signature and traces with a stylus, transferring carbon "blueprint" which is then inked over. Look for: faint carbon residue or faint underlying lines visible along strokes, hesitation/tremor as forger follows carbon blueprint, uniform line weight, possible misalignment where ink deviates from underlying carbon transfer.
  traced_indentation       - Pressure indentation / canal light effect: look for a halo (colorless depression/groove) around ink strokes where the pen pressed into paper, often visible as a depression in paper fibers. Ink may not fill the entire indented path (poor alignment). Line quality may show hesitation or tremor rather than natural fluidity.
  traced_projection        - Projection tracing: forger projects a genuine signature onto the target document using a light table, transparency projector, camera lucida, or digital projector, then inks over the projected lines. Exhibits uniform/monotonous pen pressure, micro-tremors from following a visual guide, frequent pen lifts causing ink blobs or overlapping strokes, no carbon residue, no physical indentation grooves. The signature may be a suspiciously perfect match to the original.
    ⚠ CRITICAL DISTINCTION from digital_cut_paste: traced_projection means someone PHYSICALLY DREW over a projected image - the ink strokes exist in real ink on paper, showing tremor and hesitation. digital_cut_paste means the signature was lifted digitally and composited - no physical ink was applied, and you will see a halo, pixelation, or edge artefact at the boundary. If you see a digital halo, fringe, or compression artefact around a signature, classify as digital_cut_paste, NOT traced_projection.
    ⚠ CRITICAL DISTINCTION from digital_scanned: traced_projection means real ink physically drawn on paper - the signature interacts with paper fibers, bleeds slightly into them, and shows actual pen pressure marks. digital_scanned means the document was scanned first, then a signature was digitally composited onto the scan image - the signature sits ON TOP of scan grain/noise (it looks flat, clean, or unnaturally sharp against a grainy background). Key test: does the background paper grain CONTINUE under the signature strokes, or does it stop at the edge? If the signature has no paper-fiber interaction and the scan grain is absent or interrupted beneath it, classify as digital_scanned, NOT traced_projection. Also check: is the signature perfectly level while the rest of the document has a slight scan skew? That mismatch = digital_scanned.

  CORE RULE FOR TRACED CATEGORIES:
    Traced forgeries involve REAL INK on PAPER - the physical pen marks themselves show the forgery method. Only classify as traced (any of the three types) when you can see actual ink marks with:
    - Carbon residue, indentation grooves, or tremor/hesitation in the pen strokes themselves; OR
    - Pen pressure variation (or LACK thereof) that contradicts confident natural writing; OR
    - Specific evidence of the tracing method (projected image misalignment, carbon underlay, groove pattern).
    Do NOT classify as traced merely because text "looks mechanical" or typography is "perfect" - that alone indicates digital_desktop.

Alteration:
  addition_insertion       - One or more characters were added INSIDE an existing word or number on a genuine document to change its meaning or value. There are TWO subtypes - both are addition_insertion:

    SUBTYPE A - NEW DIGIT INSERTED IN BLANK SPACE (e.g. "9,000" → "49,000"):
    - CROWDING / TIGHT SPACING: the inserted character is squeezed uncomfortably close to adjacent characters or to a currency symbol (₱, $, etc.). Authentic writers leave consistent natural spacing; forgers must squeeze a new digit into whatever gap was left.
    - INK DENSITY OR COLOR MISMATCH: the inserted character may appear slightly darker, lighter, thicker, or a different hue than surrounding original digits - forgers rarely match the exact pen used.
    - STROKE RHYTHM INCONSISTENCY: compare the slant, speed-taper, and formation of the suspect character against adjacent characters. Inserted strokes often show more hesitation, a different slant angle, or different pressure taper than the original writing event.
    - BASELINE MISALIGNMENT: the inserted character may sit slightly above or below the baseline of surrounding text.
    - LOGICAL VALUE CONFLICT: on checks and official forms, the numerical amount field and the written-out amount (words) line must match. If they don't match, this is a high-confidence indicator of numeric alteration - always check both fields when analyzing checks.

    SUBTYPE B - CHARACTER CONVERTED BY ADDING A STROKE (e.g. "3" → "8", "1" → "4", "0" → "8" or "9"):
    - INK TEXTURE MISMATCH (strongest indicator): the original character is printed toner or inkjet dots (smooth, uniform texture); the added stroke is liquid ballpoint or gel ink (wet-looking, jagged edges, different sheen). These have completely different luminance and texture even at normal scan resolution - a smooth printed character interrupted by a wet, darker manual stroke is the primary tell.
    - STROKE LAYERING / Z-AXIS: the added manual ink stroke sits visibly ON TOP of the printed character - it obscures the printed texture underneath it. In a genuine printout, all parts of a character are created simultaneously and have uniform texture throughout. Any stroke that appears to cover or overlap an existing printed region was added later.
    - MORPHOLOGICAL INCONSISTENCY: the arc or curve of the added stroke does not match the mathematical geometry of the surrounding font. Standard fonts have consistent radii and proportions; a manually added stroke almost always deviates from that geometry, creating an asymmetrical or jagged shape.
    - COMMON CONVERSION TARGETS: 3→8 (add a closing arc), 1→4 (add a crossbar and stem), 0→8 or 0→9 (add a crossbar), 7→1 (shorten), 5→6 (add a loop). When you see any of these specific digit shapes, specifically check for ink texture inconsistency on the added portion.

    PAPER SURFACE RULE: In addition_insertion the original paper surface is INTACT. The forger adds ink without removing anything. If the paper shows scuffing, thinning, fiber disruption, halos, or chemical staining, look at erasure_mechanical or erasure_chemical instead - those involve removing the original before adding new content. The core logic difference: insertion = "mutates" a character (3→8, 1→4) by adding strokes; erasure+substitution = "replaces" a character (John→Joan) by removing and rewriting.

    HYBRID FORGERY PATTERN (both subtypes): addition_insertion always occurs on otherwise authentic, genuine documents. The rest of the document (bank printing, MICR line, form template) will look real while only a small section shows the seam between original and added ink.
    ⚠ On bank checks, pay special attention to: (a) the numeric amount box - a leading digit squeezed against the currency symbol (subtype A), or a digit whose shape looks geometrically wrong with a different ink texture (subtype B); (b) the payee name line - a surname or suffix may be appended; (c) the date field - a year digit may be changed.
  addition_interlineation  - New writing squeezed BETWEEN existing lines of text (not inside a word, but in the whitespace between lines). Look for: text that is smaller or at a different baseline than surrounding lines, ink that differs from surrounding lines, spacing that is unnaturally compressed around the inserted line.
  erasure_chemical         - Original ink was removed using a chemical solvent (ink eradicator, bleach, acetone), often followed by new text written or printed in the cleaned area. This is a two-step substitution: remove original → replace with new. Key indicators:
    - HALO / TIDE MARK: a faint circular or irregular discoloration where the solvent spread beyond the target area, leaving a chemical residue ring on the paper.
    - INK GHOSTING: a faint shadow or "ghost" of the original character remains visible - solvents rarely remove 100% of the ink, especially from bond paper.
    - PAPER FIBER DAMAGE: solvent weakens the paper surface, causing slight translucency or a matte patch that reflects light differently from the surrounding area.
    - NEW TEXT ON DAMAGED BACKGROUND: the replacement text sits on a patch that looks clean but wrong - the paper's natural texture or aging is disrupted beneath the new characters.
    - UNDER OBLIQUE LIGHT: the erased area shows a dull or shiny patch inconsistent with surrounding paper reflectance.
    ⚠ DISTINCTION from addition_insertion: chemical erasure involves removing the original character FIRST (paper shows residue, ghost, or halo). addition_insertion leaves the original character intact and adds ink on top of it (paper surface is undamaged; the forgery is purely in the ink layer).

  erasure_mechanical       - Original ink was physically scraped off using a razor blade, sandpaper, eraser, or knife, often followed by new text written or printed on the scraped area. This is a two-step substitution: abrade original → replace with new. Key indicators:
    - ABRADED / SCUFFED PAPER FIBERS ("FUZZY PATCH"): the paper surface is visibly roughened - it looks "fuzzy," "pilled," or matted compared to the smooth surrounding paper. This is the strongest visible tell under normal lighting.
    - SHADOW PATCH / SHEEN DIFFERENCE: the erased area reflects light differently from the rest of the document - it may appear darker, lighter, or matte where the surrounding paper is glossy (or vice versa). In a scan this often appears as a gray-level patch that doesn't match the blank paper around it.
    - GHOST PARTICLES / RESIDUAL INK: mechanical scraping cannot remove 100% of the ink - tiny pigment particles become trapped deep in the disturbed fibers, leaving a dark smudge or shadow in the general shape of the original character. This ghost is NOT as sharp as a real character but has the right rough outline.
    - PAPER THINNING: repeated scraping thins the paper - in transmitted light (backlit) the erased area appears brighter or more translucent than surrounding paper.
    - JAGGED / UNEVEN VOID BOUNDARY: the damage zone has rough, irregular edges - unlike a clean erased area, the boundary between damaged and undamaged paper is jagged because the abrasive tool didn't scrape in a perfectly controlled path.
    - INK FEATHERING ON REPLACEMENT TEXT: new ink written on abraded paper bleeds or feathers into the damaged fibers - the sizing (paper coating) that normally keeps ink crisp has been destroyed by the scraping.
    - LOGICAL WORD TRUNCATION: if a word appears incomplete or truncated (e.g., "RENSIC" instead of "FORENSIC"), and there is a localized paper damage zone at the exact point of truncation, the missing characters were mechanically erased. Check whether the remaining text forms a logical word/name - if not, characters are missing.
    ⚠ DISTINCTION from erasure_chemical: mechanical erasure shows PHYSICAL fiber damage (rough, pilled surface). Chemical erasure uses a solvent and leaves the surface smoother but stained or with a tide mark; new ink bleeds from paper sizing loss, not from fiber disruption.
    ⚠ DISTINCTION from addition_insertion: mechanical erasure is visible as surface damage to the paper itself (scuffing, thinning, fiber disruption). addition_insertion has NO paper surface damage - the original character is still intact; only a new ink stroke was layered on top.

Cut and Paste / Digital Fabrication:
  digital_cut_paste        - A genuine element (signature, stamp, photo, text block) was digitally lifted from one document and composited onto this one using Photoshop, GIMP, or a PDF editor. Key indicators:
    - HALO / FRINGE: a thin bright or differently-coloured edge around the pasted element - caused by anti-aliasing or colour-mismatch during compositing. This is the single strongest DTP indicator.
    - PIXELATION / ALIASING: jagged or blurry edges along the pasted element's boundary, especially visible on diagonal or curved strokes of a signature.
    - BACKGROUND INCONSISTENCY: the paper texture, grain, or colour under the pasted element differs from the surrounding area - looks like a different piece of paper was inserted.
    - COMPRESSION ARTEFACTS: JPEG blocking or noise concentrated around one specific element while the rest of the document is clean.
    - DPI / RESOLUTION MISMATCH: pasted element is noticeably sharper or blurrier than surrounding printed text.
    - SHADOW / LIGHTING: cast shadow direction, document reflections, or paper thickness inconsistent with the rest.
    - LEVELLING: pasted signature or stamp is too perfectly level or centred relative to surrounding text - originates from software alignment tools.
    ⚠ CRITICAL DISTINCTION from traced_projection: digital_cut_paste shows DIGITAL artefacts (halos, pixelation, compression noise, colour-boundary mismatch). Traced forgeries show PHYSICAL artefacts (tremor, hesitation, slow monotonous stroke, no digital halo). A clear digital halo around a signature IS digital_cut_paste even if the signature strokes themselves look fluid.
  digital_desktop          - The ENTIRE document (or a large section) was fabricated from scratch using word-processing or design software (Microsoft Word, Google Docs, Canva, Photoshop) rather than physically typed or printed on authentic forms. Key indicators:
    - PERFECT DIGITAL TYPOGRAPHY: computer-perfect font spacing, kerning, and alignment throughout. Every character was generated by a single font engine at a single print run - no hand-written variation, no typewriter key-strike impression, no pressure variation in ink. This is the strongest DTP indicator.
    - FONT CONSISTENCY ACROSS ENTIRE DOCUMENT: a single font family used uniformly (or deliberately mixed fonts in designed document). If a document purports to be a real physical form (bank letter, government ID, handwritten memo), but ALL text shows identical font rendering and spacing, it was likely created digitally.
    - FORMS & TEMPLATES: document layout exactly matches common Microsoft Word, Google Docs, or Canva templates - pre-built borders, logos, text boxes, or columns in stock positions.
    - SIGNATURE QUALITY MISMATCH: if a hand-written or scanned signature sits on otherwise pristine digital text with zero interaction (no ink bleed, no pressure marks), the signature was composited onto digital text - strong DTP indicator.
    - ZERO PHYSICAL REALISM: official documents (government IDs, bank checks, certificates) show security features (watermarks, microtext, embossed seals, color gradients, microprinting). Complete absence of these on what claims to be official = suspicious digital fabrication.
    ⚠ CRITICAL DISTINCTION from digital_cut_paste: digital_desktop means the ENTIRE document is fabricated software-to-paper; digital_cut_paste means one element was inserted into an otherwise genuine document.
    ⚠ CRITICAL DISTINCTION from traced categories: If the document shows perfect digital typography and font consistency, classify as digital_desktop, NOT traced_projection or traced_indentation. Traced methods involve hand-drawn ink on paper; perfect typography indicates software generation.
  digital_scanned          - A real physical document was scanned, then digital elements were composited onto the scan image (stamp, signature, name field, or date added in an image editor), and the result was re-saved or re-printed. Key indicators:
    - NOISE INCONSISTENCY: an authentic scan has uniform "salt-and-pepper" scanner noise across the entire sheet. Digitally added elements sit ON TOP of this noise - they look artificially clean or sharp against a grainy background. Natural blank paper areas look uniformly noisy; areas around inserted elements look "erased" or unnaturally smooth.
    - STAMP / SIGNATURE FLATNESS: a genuine wet-ink stamp or signature pressed onto physical paper bleeds into paper fibers and interacts with existing ink. A digitally overlaid stamp or signature looks "flat" - no fiber absorption, no slight ink bleed, no interaction with underlying printed text where they overlap.
    - GLOBAL SCAN TILT vs. LOCAL ELEMENT ALIGNMENT: a real scanner captures the whole page with the same perspective/tilt. If the main document body has a slight skew but a stamp or signature is perfectly level (or vice versa), the element was inserted digitally AFTER scanning - it did not go through the same scanner geometry.
    - COMPRESSION LEVEL MISMATCH (ELA): JPEG compression artifacts cluster around digitally added elements at a different level than the surrounding scanned paper - the base scan was compressed once, the overlay was compressed again on re-save.
    - RESOLUTION HALO: the boundary between the scanned paper grain and the digitally inserted element shows a subtle halo or transition band where the two layers were blended.
    - FONT / FIELD INCONSISTENCY: student or employee names, ID numbers, or dates typed in a slightly different font weight, spacing, or DPI than the pre-printed form template - the template was digitally re-filled after scanning.
    ⚠ DISTINCTION from digital_cut_paste: digital_scanned uses a REAL SCANNED DOCUMENT as the base and adds elements on top of the scan. digital_cut_paste pastes elements into an otherwise authentic document. Choose digital_scanned when the underlying base is clearly a real scan (paper grain, scanner shadow, uniform noise) and the tampered elements sit on top of that grain.

Obliteration:
  obliteration_ink         - Original text scribbled out with ink.
  obliteration_whiteout    - Correction fluid covering text.

Sympathetic Ink:
  sympathetic_indented     - Indented writing visible only via raking light. Pressure indentations on paper with no visible ink.
  sympathetic_special      - Invisible/special ink revealed by an external stimulus (heat, chemical reagent, or UV light). When you detect this, you MUST identify the likely substance based on visible cues:
    HEAT-ACTIVATED (browned/charred organic substance - most common):
      - Lemon/citrus juice: brown strokes, slight crystalline residue
      - Milk: brown strokes, possible greasy/translucent appearance
      - Sugar water / honey: dark brown to black, glossy carbonized look
      - Onion juice / vinegar: pale brown, sharp smell association
      - Wax / crayon resist: waxy sheen, repels later ink/water
    CHEMICALLY-ACTIVATED (color reaction from reagent):
      - Phenolphthalein + ammonia → bright pink/magenta strokes
      - Cobalt chloride + heat → blue→pink color shift
      - Starch + iodine → dark blue/purple strokes
    UV/FLUORESCENT (only visible under UV light):
      - Security ink, quinine (tonic water), highlighter residue → glowing strokes under blacklight
    Put the specific substance in the "subtype" field (e.g., "lemon juice", "milk", "phenolphthalein", "UV ink"). State the substance and method explicitly in the explanation. If genuinely unsure, say so but propose the most likely candidate based on color, texture, and any charring pattern.
    ⚠ DISTINCTION from erasure_mechanical: Mechanical erasure leaves a GHOST of text that WAS THERE and was removed - the paper surface will be roughened/disturbed and the faint remnants are irregular. Sympathetic ink reveals text that was ALWAYS HIDDEN - the paper surface is undisturbed and the strokes are uniformly faint. If there is also NEW text written over the faint area (suggesting erase-then-rewrite), choose erasure_mechanical, not sympathetic_special.

Currency:
  currency_analysis        - Suspected counterfeit banknote.

Fallbacks (use ONLY when nothing above fits):
  no_forgery_detected      - Document looks authentic, no tampering signs.
  not_a_document           - Image is not a document at all (selfie, meme, screenshot).
  other                    - Real forgery that does NOT match any of the 15 specific types. Do NOT use this if the forgery matches a specific category - even partially. For example: if you identify traced_projection, use traced_projection, not other with subtype traced_projection.

═══════════════════════════════════════════════════════════════════════════
IGNORE these (they are NOT forgery indicators):
  - Phone-camera blur, low resolution, poor lighting, shadows from the photographer
  - Background surface (desk, hands, clutter behind the document)
  - JPEG compression noise on the entire image (this is normal)
  - Worn paper, creases, folds, age stains, coffee marks (these are wear, not forgery)
  - Watermark patterns and security features that are SUPPOSED to be there
  - Slight rotation, perspective skew, glare from flash
═══════════════════════════════════════════════════════════════════════════

REASONING - work through these steps in order before you classify:
  1. What is in the image? (document or non-document; if document, what type?)
  2. Scan the WHOLE document for anomalies. List EVERY anomaly you see - do not stop at the first one.
  3. For each anomaly, ask: is this real tampering, or one of the IGNORE items above?
  4. CRITICAL BRANCHING QUESTION: Can I see PHYSICAL PEN MARKS or HAND-DRAWN INK EVIDENCE (grooves, tremor, hesitation, carbon residue)? OR is this PERFECT DIGITAL TYPOGRAPHY (uniform font, zero pen variation)?
     - YES (pen marks visible) → consider traced_carbon, traced_indentation, traced_projection
     - NO (perfect digital typography) → consider digital_desktop, digital_cut_paste, digital_scanned
  5. If there are MULTIPLE anomalies within your chosen branch, decide which is the PRIMARY forgery (the one that changes the document's legal meaning).
  6. Point to the PRIMARY anomaly's LOCATION (which region of the document).
  7. Pick the single best category code based on the PRIMARY evidence.
  8. Set confidence based on how clear the evidence is (see scale below).
  ⚠ BANK CHECK RULE: When analyzing a check, always compare the numeric amount field AND the written-out pesos/dollars line. If they don't match, or if a digit appears squeezed against the currency symbol, classify as addition_insertion even if other anomalies (like a smudge or lighter patch) also exist.
  ⚠ INK LAYERING RULE: On any document with printed (toner/inkjet) text, if you see a stroke or mark that has a different texture, sheen, or "wetness" than the surrounding printed characters - especially if it appears to sit ON TOP of the printed text - this is addition_insertion (subtype B: character conversion). Do NOT classify abrasion or disrupted paper fiber as erasure_mechanical if the dominant anomaly is a visually different ink stroke overlaid on top of printed text.
  ⚠ INCOMPLETE WORD RULE: If a word or name appears to be missing characters at one end or in the middle, AND there is a patch of paper damage (roughened surface, shadow patch, ghost smudge) at exactly the gap, classify as erasure_mechanical. A word that cannot stand alone as a real word but would be a real word if characters were prepended is a strong signal (e.g., "RENSIC" → "FORENSIC", "OAN" → "LOAN").
  ⚠ SEMANTIC CONFLICT / CHEMICAL ERASURE RULE: If the written-out amount (e.g., "THREE THOUSAND") does NOT match the numeric field (e.g., "000" with a smudge where the leading digit should be), a leading digit was likely chemically erased. Ink eradicator dissolves the original digit, causing the new ink applied in the cleaned spot to bleed and feather into the damaged paper sizing - this creates dark smudges or halos at the edges of the erased area that can look like obliteration_ink. Key distinguisher: obliteration_ink smears cover text intentionally; erasure_chemical smears appear at the EDGE of a blank area where a character USED TO BE. If the smudge is adjacent to missing/blank space where a digit is expected (based on the written-out amount), classify as erasure_chemical, not obliteration_ink.
  ⚠ GHOST TEXT vs. SYMPATHETIC INK RULE: Faint, discolored, or brownish text can mean EITHER mechanical erasure (a ghost of what was removed) OR sympathetic ink (hidden writing being revealed). Apply this branching test before classifying:
    SYMPATHETIC INK signals - choose sympathetic_special when ALL of these hold:
      1. The faint text appears in an area where the paper surface is CLEAN and undisturbed (no fiber roughening, no sheen change, no shadow patch).
      2. The faint strokes are UNIFORMLY faint across all characters - consistent activation level, as if written with the same substance throughout.
      3. There is NO normal/visible text written OVER or BESIDE the faint area - the hidden text stands alone in space that was otherwise blank.
      4. The document context does NOT require text to be there (this text is extra, not a replacement).
    MECHANICAL ERASURE signals - choose erasure_mechanical when ANY of these hold:
      1. The paper surface in the faint-text area looks different from surrounding paper: rougher, fuzzier, duller sheen, or shadow patch (physical fiber damage from abrasion).
      2. There is BOTH a faint ghost AND new text written or printed over that same area - someone erased the original and wrote something new on top.
      3. The document CONTEXT demands that text exist in that location (e.g., a name field, amount field, date field) AND the visible text there does not match what the ghost suggests.
      4. The ghost strokes are IRREGULAR - some characters partially remain, others are nearly gone, with uneven remnant intensity from imperfect abrasion.
    KEY TIE-BREAKER: Sympathetic ink text APPEARS (was invisible, now revealed). Erasure ghost text DISAPPEARS (was visible, now partially gone). If the surrounding context clearly shows the text was there before and is now missing or replaced, classify as erasure_mechanical - NOT sympathetic_special.

CONFIDENCE SCALE (be honest - overconfidence is hallucination):
  0.90–1.00  Multiple unambiguous signs of this exact forgery type
  0.70–0.89  Clear signs but some ambiguity
  0.50–0.69  Suspicious but not definitive - could be benign
  0.30–0.49  Weak signal; mention it but lean toward no_forgery_detected
  0.00–0.29  No real evidence; classify as no_forgery_detected unless you saw something

OUTPUT - return ONLY valid JSON, no markdown fences, no prose outside the object:

{
  "reasoning_steps": [
    "<step 1: what's in the image>",
    "<step 2: anomalies observed>",
    "<step 3: filtered against ignore list>",
    "<step 4: hand-drawn ink or digital typography? (CRITICAL BRANCHING)>",
    "<step 5: which category in the chosen branch, and why>",
    "<step 6: location of evidence>",
    "<step 7: primary vs alternatives>",
    "<step 8: confidence and remaining ambiguity>"
  ],
  "category": "<one code from the list>",
  "subtype": "<specific kind, or null>",
  "confidence": <float 0.0–1.0 per scale above>,
  "anomaly_location": "<where on the document the forgery appears, e.g. 'top-right date field' - null if no_forgery_detected or not_a_document>",
  "explanation": "<MUST start with the human-readable category name, then explain why based on visible cues>",
  "evidence": ["<short visible cue>", "<another>", "..."],
  "tools_likely_used": "<what tools/methods, or null if not applicable>",
  "alternatives": [
    {"category": "<code>", "reasoning": "<one sentence: what evidence points toward this, and what makes the primary more likely>"},
    {"category": "<code>", "reasoning": "<...>"}
  ]
}

CRITICAL RULES:
  1. The "explanation" MUST begin with the category's human name (e.g. "Chemical Erasure detected.").
  2. If you classify as no_forgery_detected, set anomaly_location to null and evidence to [] or just observed-clean items.
  3. Do NOT invent evidence. If you can't see it, don't list it.
  4. Pick exactly ONE category. If torn, pick the dominant one and mention the other in the alternatives array.
  5. Output ONLY the JSON object. No code fences, no commentary.
  6. "alternatives" must be a JSON array (never null - use [] if there are none). Include up to 3 alternatives ordered by likelihood. Populate it whenever: confidence is below 0.90, OR multiple categories fit the evidence almost equally, OR image quality limits certainty. Leave it as [] only when the evidence is completely unambiguous. Be honest - it is better to admit ambiguity than to over-commit."""


# ═══════════════════════════════════════════════════════════════════════════
# AUXILIARY PROMPTS
# Used by the optimization pipeline functions defined below in this file.
# ═══════════════════════════════════════════════════════════════════════════

# ───────────────────────────────────────────────────────────────────────────
# TRIAGE_PROMPT - Stage 1 quick classification (~700 tokens, $0.00005)
# Used by triage_classify() to seed alternatives in the main result.
# ───────────────────────────────────────────────────────────────────────────

TRIAGE_PROMPT = """You are a forensic document examiner doing a quick triage classification.

Look at this document and pick the TOP 3 most likely forgery categories.

Categories (code - name):
  traced_carbon           - Carbon transfer
  traced_indentation      - Indentation grooves / canal light
  traced_projection       - Projection tracing
  addition_insertion      - Characters inserted into numbers/words
  addition_interlineation - Text squeezed between lines
  erasure_chemical        - Solvent-erased then rewritten
  erasure_mechanical      - Scraped then rewritten
  digital_cut_paste       - Signature/element pasted in (halo, pixelation)
  digital_desktop         - Entire document fabricated in software
  digital_scanned         - Real scan with digital elements added
  obliteration_ink        - Text scribbled over
  obliteration_whiteout   - Correction fluid
  sympathetic_indented    - Indented writing under raking light
  sympathetic_special     - Hidden ink (invisible, UV, heat-activated)
  currency_analysis       - Counterfeit currency
  no_forgery_detected     - Authentic document
  not_a_document          - Not a document
  other                   - Other forgery

Return ONLY valid JSON:
{
  "top_3": ["category_code", "category_code", "category_code"],
  "reasoning": "brief reason why these three"
}
"""


# ───────────────────────────────────────────────────────────────────────────
# CATEGORY_DETAIL - Per-category detail dictionary
# Used by build_detailed_prompt() to construct a focused prompt that only
# describes the top-3 categories from triage (saves text tokens).
# ───────────────────────────────────────────────────────────────────────────

CATEGORY_DETAIL = {
    "traced_carbon": """
    traced_carbon - Carbon-paper transfer: forger places carbon under a genuine signature and traces, transferring carbon which is then inked over.
    Look for: faint carbon residue, hesitation/tremor, uniform line weight, possible misalignment.
    """,

    "traced_indentation": """
    traced_indentation - Pressure indentation / canal light: look for colorless depression (groove/halo) around ink strokes where pen pressed into paper.
    Look for: depression in fibers, ink not filling entire path, hesitation, tremor rather than natural fluidity.
    """,

    "traced_projection": """
    traced_projection - Projection tracing: forger projects genuine signature using light table/projector, then inks over projected lines.
    Look for: uniform/monotonous pen pressure, micro-tremors, frequent pen lifts, no carbon residue, no physical grooves, suspiciously perfect match.
    """,

    "addition_insertion": """
    addition_insertion - One or more characters added to change meaning/value. Two subtypes:
    A) Digit inserted in blank space (e.g., "9,000" → "49,000"): cramped spacing, ink/color mismatch, inconsistent stroke rhythm, baseline misalignment.
    B) Character converted by adding stroke (e.g., "3" → "8"): ink texture mismatch (printed vs. wet ink), layering/z-axis, morphological inconsistency.
    """,

    "addition_interlineation": """
    addition_interlineation - New writing squeezed between existing lines of text (in whitespace between lines, not inside a word).
    Look for: smaller text, different baseline, ink differs from surrounding lines, unnaturally compressed spacing.
    """,

    "erasure_chemical": """
    erasure_chemical - Original ink removed using solvent (bleach, acetone, eradicator), followed by new text written/printed.
    Look for: halo/tide mark (circular discoloration), ink ghosting (faint shadow of original), paper fiber damage, matte patch, under oblique light: dull or shiny patch.
    """,

    "erasure_mechanical": """
    erasure_mechanical - Original ink scraped off using razor/sandpaper/eraser, followed by new text written/printed.
    Look for: abraded/scuffed fibers ("fuzzy patch"), shadow patch/sheen difference, ghost particles/residual ink, paper thinning, jagged void boundary, ink feathering.
    """,

    "digital_cut_paste": """
    digital_cut_paste - Genuine element (signature, stamp, photo, text) digitally lifted from one document and pasted onto this one.
    Look for: HALO/FRINGE (thin bright edge, strongest DTP indicator), pixelation/aliasing, background inconsistency, compression artifacts, DPI mismatch, shadow/lighting inconsistency.
    ⚠️ CRITICAL: digital_cut_paste shows DIGITAL artifacts (halos, pixelation). Traced forgeries show PHYSICAL artifacts (tremor, hesitation, no halo).
    """,

    "digital_desktop": """
    digital_desktop - ENTIRE document (or large section) fabricated from scratch using Word/Docs/Canva/Photoshop.
    Look for: perfect digital typography, font inconsistency, generic templates, signature quality contrast, inkjet/laser print pattern, NO physical form elements.
    """,

    "digital_scanned": """
    digital_scanned - Real physical document scanned, then digital elements composited onto the scan image (stamp, signature, name, date).
    Look for: noise inconsistency (inserted elements look unnaturally clean/sharp), stamp flatness (no fiber absorption), global tilt vs. local alignment, compression level mismatch, resolution halo.
    """,

    "obliteration_ink": """
    obliteration_ink - Original text scribbled out with ink.
    """,

    "obliteration_whiteout": """
    obliteration_whiteout - Correction fluid covering text.
    """,

    "sympathetic_indented": """
    sympathetic_indented - Indented writing visible only via raking light. Pressure indentations on paper with no visible ink.
    """,

    "sympathetic_special": """
    sympathetic_special - Invisible/special ink revealed by external stimulus (heat, UV, chemical reagent).
    If detected, identify likely substance: lemon/milk/sugar (heat-activated brown), phenolphthalein (pink), cobalt chloride (blue→pink), starch+iodine (dark blue), quinine/security ink (UV fluorescent).
    """,

    "currency_analysis": """
    currency_analysis - Suspected counterfeit banknote.
    """,

    "no_forgery_detected": """
    no_forgery_detected - Document looks authentic, no tampering signs.
    """,

    "not_a_document": """
    not_a_document - Image is not a document (selfie, meme, screenshot).
    """,

    "other": """
    other - Real forgery that does NOT match any specific category. Only use if the forgery genuinely does not fit elsewhere.
    """,
}


# ───────────────────────────────────────────────────────────────────────────
# DETAILED_PROMPT_TEMPLATE - Stage 2 (focused) classification
# Currently NOT used by the analyze route (we run full SYSTEM_PROMPT instead),
# but kept available for narrowed-analysis experiments. The {category_descriptions}
# placeholder is filled by build_detailed_prompt() with the top-3 categories.
# ───────────────────────────────────────────────────────────────────────────

DETAILED_PROMPT_TEMPLATE = """You are a forensic document examiner. Classify the image into EXACTLY ONE of the categories below.

CATEGORIES (analyze only these, all others are irrelevant):
{category_descriptions}

REASONING - work through these steps before classifying:
  1. What is in the image? (document or non-document)
  2. Scan the WHOLE document for anomalies.
  3. For each anomaly, ask: is this real tampering or normal wear/lighting?
  4. Point to the PRIMARY anomaly's LOCATION.
  5. Pick the single best category based on PRIMARY evidence.
  6. Set confidence based on evidence clarity.

CONFIDENCE SCALE:
  0.90–1.00  Multiple unambiguous signs
  0.70–0.89  Clear signs but some ambiguity
  0.50–0.69  Suspicious but not definitive
  0.30–0.49  Weak signal
  0.00–0.29  No real evidence → classify as no_forgery_detected

OUTPUT - return ONLY valid JSON, no markdown:
{{
  "reasoning_steps": [
    "<step 1>",
    "<step 2>",
    "<step 3>",
    "<step 4>",
    "<step 5>",
    "<step 6>"
  ],
  "category": "<category code>",
  "subtype": "<specific kind or null>",
  "confidence": <float 0.0–1.0>,
  "anomaly_location": "<where on document or null>",
  "explanation": "<human readable name + why>",
  "evidence": ["<cue>", "<cue>"],
  "tools_likely_used": "<tools or null>",
  "alternatives": [
    {{"category": "<code>", "reasoning": "<why less likely>"}},
    {{"category": "<code>", "reasoning": "<why less likely>"}}
  ]
}}
"""


# ───────────────────────────────────────────────────────────────────────────
# CRITIQUE_PROMPT_TEMPLATE - Stage 3 (self-critique) when confidence is medium
# Used by confidence_gated_analyze() to verify or reject the primary verdict.
# ───────────────────────────────────────────────────────────────────────────

CRITIQUE_PROMPT_TEMPLATE = """You are a second reviewer checking a forensic classification.

Original classification: {original_category} (confidence: {original_confidence})
Reasoning: {original_reasoning}
Evidence: {original_evidence}

Looking at this document, do you agree with the above classification?

Return JSON:
{{
  "agrees": true or false,
  "reasoning": "brief explanation",
  "alternative_category": "if disagree, what category instead (or null)",
  "alternative_confidence": <0.0-1.0 or null>
}}
"""


def _build_user_context_block(
    document_type: Optional[str],
    suspicion_reason: Optional[str],
    area_of_concern: Optional[str],
    image_source: Optional[str],
    is_forged_belief: Optional[str],
    shot_type: Optional[str],
    lighting: Optional[str],
    physical_clues: Optional[str],
) -> str:
    """Build an optional user-context block. Returns empty string if no context."""
    lines = []
    if document_type and document_type not in ("other", "", None):
        lines.append(f"- Document type (per user): {document_type.replace('_', ' ')}")
    if image_source and image_source not in ("not_sure", "", None):
        lines.append(f"- Image source (per user): {image_source.replace('_', ' ')}")
    if shot_type and shot_type not in ("not_sure", "", None):
        lines.append(f"- Shot type (per user): {shot_type.replace('_', ' ')}")
    if lighting and lighting not in ("not_sure", "", None):
        lines.append(f"- Lighting condition (per user): {lighting.replace('_', ' ')}")
    if is_forged_belief and is_forged_belief not in ("not_sure", "", None):
        lines.append(f"- User's belief about authenticity: {is_forged_belief.replace('_', ' ')}")
    if area_of_concern and area_of_concern not in ("anywhere", "", None):
        lines.append(f"- User wants you to focus on: {area_of_concern.replace('_', ' ')}")
    if physical_clues and physical_clues not in ("none", "", None):
        _clue_labels = {
            "indentation_grooves": "indentation grooves / canal marks behind writing",
            "carbon_streaks": "faint carbon residue along strokes",
            "uniform_traced_lines": "uniform line weight (looks traced)",
            "ink_halo": "halo or discoloration around erased area",
            "paper_thinning": "thinned or abraded paper surface",
            "characters_inserted": "extra characters squeezed inside words/numbers",
            "text_between_lines": "writing squeezed between existing lines",
            "cut_paste_edges": "visible cut/paste edges or texture mismatch",
            "whiteout_correction": "correction fluid covering text",
            "ink_scribbles": "ink scribbled over original text",
            "counterfeit_currency": "suspect counterfeit banknote",
            "computer_generated": "looks computer-generated / desktop-published",
            "scan_tampering_artifacts": "scanned document with visible digital edits layered on top",
            "sympathetic_hidden_writing": "hidden writing only visible under special lighting (UV, raking, backlight) - check for sympathetic_indented",
            "uv_reactive_ink_glow": "ink glows or reacts under UV light - check for sympathetic_special",
        }
        clue_label = _clue_labels.get(physical_clues, physical_clues.replace('_', ' '))
        lines.append(f"- Physical clue user thinks they observed: {clue_label}")
    if suspicion_reason:
        clean = suspicion_reason.strip()[:300]
        if clean:
            lines.append(f"- User's suspicion in their own words: \"{clean}\"")
    if not lines:
        return ""
    return (
        "\n\n═══════════════════════════════════════════════════════════════════════════\n"
        "USER-PROVIDED CONTEXT - TREAT AS HINTS ONLY, NOT FACTS:\n\n"
        + "\n".join(lines)
        + "\n\nHOW TO USE THIS CONTEXT:\n"
        "  - The IMAGE is the ultimate evidence. The user's hints are just guidance.\n"
        "  - Verify every user claim against what you actually see in the image.\n"
        "  - If the user says \"indentation grooves visible\" but the image shows clean text\n"
        "    with no grooves, IGNORE the user's hint and classify based on what you see.\n"
        "  - If the user says \"this is forged\" but the document looks completely authentic,\n"
        "    classify as no_forgery_detected - do not be pressured by their belief.\n"
        "  - User hints can help you LEAN toward a category when the visible evidence is\n"
        "    ambiguous, but they cannot CREATE evidence that isn't there.\n"
        "  - When the user's hint contradicts the image, note this in your reasoning_steps.\n"
        "═══════════════════════════════════════════════════════════════════════════"
    )


def _client(api_key: Optional[str] = None):
    key = api_key or GEMINI_API_KEY
    if not key:
        return None
    try:
        from google import genai
        return genai.Client(api_key=key)
    except ImportError:
        return None


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _coerce(parsed: Dict[str, Any]) -> Dict[str, Any]:
    raw_cat = (parsed.get("category") or "").strip().lower()
    if raw_cat not in CATEGORY_CODES:
        raw_cat = "other"

    confidence = parsed.get("confidence")
    try:
        confidence = float(confidence)
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.0

    evidence = parsed.get("evidence") or []
    if not isinstance(evidence, list):
        evidence = [str(evidence)]
    evidence = [str(e).strip() for e in evidence if str(e).strip()]

    reasoning = parsed.get("reasoning_steps") or []
    if not isinstance(reasoning, list):
        reasoning = [str(reasoning)]
    reasoning = [str(r).strip() for r in reasoning if str(r).strip()]

    anomaly_location = parsed.get("anomaly_location")
    if isinstance(anomaly_location, str):
        anomaly_location = anomaly_location.strip() or None
    elif anomaly_location is not None:
        anomaly_location = str(anomaly_location).strip() or None

    # Force null on non-forgery categories - Gemini sometimes makes up locations
    if raw_cat in ("no_forgery_detected", "not_a_document"):
        anomaly_location = None

    # Alternatives array - support both new array format and legacy single-field format
    raw_alts = parsed.get("alternatives")
    if isinstance(raw_alts, list):
        alternatives = []
        for item in raw_alts:
            if not isinstance(item, dict):
                continue
            code = (item.get("category") or "").strip()
            if code not in CATEGORY_CODES:
                continue
            alternatives.append({
                "category": code,
                "category_label": CATEGORY_LABELS[code],
                "reasoning": (item.get("reasoning") or "").strip() or None,
            })
    else:
        # Legacy fallback: single alternative_category / alternative_reasoning fields
        alt_cat_raw = (parsed.get("alternative_category") or "").strip()
        alt_cat = alt_cat_raw if alt_cat_raw in CATEGORY_CODES else None
        alt_reasoning = (parsed.get("alternative_reasoning") or "").strip() or None
        alternatives = ([{
            "category": alt_cat,
            "category_label": CATEGORY_LABELS[alt_cat],
            "reasoning": alt_reasoning,
        }] if alt_cat else [])

    return {
        "category": raw_cat,
        "category_label": CATEGORY_LABELS[raw_cat],
        "subtype": (parsed.get("subtype") or "").strip() or None,
        "confidence": confidence,
        "explanation": (parsed.get("explanation") or "").strip(),
        "evidence": evidence,
        "reasoning_steps": reasoning,
        "anomaly_location": anomaly_location,
        "tools_likely_used": (parsed.get("tools_likely_used") or "").strip() or None,
        "certainty_level": "HIGH" if confidence >= 0.85 else "MEDIUM" if confidence >= 0.60 else "LOW",
        "alternatives": alternatives,
        "model_used": None,
    }


def _fallback(reason: str) -> Dict[str, Any]:
    return {
        "category": "other",
        "category_label": CATEGORY_LABELS["other"],
        "subtype": None,
        "confidence": 0.0,
        "explanation": f"Gemini Vision was unavailable: {reason}",
        "evidence": [],
        "reasoning_steps": [],
        "anomaly_location": None,
        "tools_likely_used": None,
        "_unavailable": True,
    }


def classify(
    image: Image.Image,
    document_type: Optional[str] = None,
    suspicion_reason: Optional[str] = None,
    area_of_concern: Optional[str] = None,
    image_source: Optional[str] = None,
    is_forged_belief: Optional[str] = None,
    shot_type: Optional[str] = None,
    lighting: Optional[str] = None,
    physical_clues: Optional[str] = None,
    use_cache: bool = False,
    system_prompt_override: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run Gemini Vision against the document image.

    All extra args are optional hints - when None or default, Gemini classifies
    purely from the image. The image is always the deciding factor.

    Args:
        use_cache: If True, use prompt caching (90% discount on system prompt for 5 min window).
        api_key: Optional user's API key. If provided, uses that instead of the backend key.
    """
    client = _client(api_key=api_key)
    if client is None:
        return _fallback("API key not configured or google-genai not installed")

    buf = io.BytesIO()
    img_to_send = image if image.mode == "RGB" else image.convert("RGB")
    img_to_send.save(buf, format="JPEG", quality=88)
    buf.seek(0)

    base_prompt = system_prompt_override if system_prompt_override else SYSTEM_PROMPT
    prompt = base_prompt + _build_user_context_block(
        document_type, suspicion_reason, area_of_concern, image_source,
        is_forged_belief, shot_type, lighting, physical_clues,
    )

    from google.genai import types as genai_types

    # Prompt caching disabled due to google-genai API issues
    # TODO: Re-enable when google-genai fixes CachedContent API
    # cached_content_name = get_or_create_cache(client, SYSTEM_PROMPT) if use_cache else None

    text = ""
    last_exc: Optional[Exception] = None
    model_used = None
    for model in _model_chain():
        try:
            contents = [
                prompt,
                genai_types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"),
            ]

            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=genai_types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                ),
            )
            text = response.text or ""
            model_used = model
            break
        except Exception as exc:
            if _is_rate_limited(exc):
                print(f"[WARN] {model} rate-limited, trying next model. ({exc})")
                last_exc = exc
                continue
            return _fallback(f"API call failed: {exc}")
    else:
        return _fallback(f"All models rate-limited: {last_exc}")

    text = _strip_json_fence(text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return _fallback("response was not valid JSON")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return _fallback("response was not valid JSON")

    if not isinstance(parsed, dict):
        return _fallback("response was not a JSON object")

    result = _coerce(parsed)
    result["model_used"] = model_used
    return result


# ───────────────────────────────────────────────────────────────────────────
# EXPLAIN-ONLY PATH - used when the local classifier is confident.
# Gemini gets a tiny prompt (the classifier already chose the category), so it
# only verifies + explains. Far fewer tokens than the full 15-category prompt.
# ───────────────────────────────────────────────────────────────────────────

EXPLAIN_PROMPT_TEMPLATE = """You are a forensic document examiner. A trained classifier identified this document as: {label}.

Confirm the SPECIFIC category from this list, judge whether it is actually forged or genuine, and explain concisely from visible evidence.
Allowed categories: {candidates}

If the image clearly does NOT match that description, say so in the explanation and use no_forgery_detected (authentic) or not_a_document (not a document).

Return ONLY valid JSON, no prose outside it:
{{
  "category": "<one allowed category code>",
  "subtype": "<specific kind or null>",
  "confidence": <float 0.0-1.0>,
  "anomaly_location": "<where the evidence is, or null>",
  "explanation": "<start with the category's human name, then the visible evidence>",
  "evidence": ["<short visible cue>", "<another>"]
}}"""


def explain_with_hint(
    image: Image.Image,
    label: str,
    candidates: list[str],
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Short verify-and-explain call given a category the local classifier chose."""
    client = _client(api_key=api_key)
    if client is None:
        return _fallback("API key not configured or google-genai not installed")

    buf = io.BytesIO()
    (image if image.mode == "RGB" else image.convert("RGB")).save(buf, format="JPEG", quality=88)
    buf.seek(0)

    allowed = list(candidates) + ["no_forgery_detected", "not_a_document"]
    prompt = EXPLAIN_PROMPT_TEMPLATE.format(label=label, candidates=", ".join(allowed))

    from google.genai import types as genai_types
    text = ""
    last_exc: Optional[Exception] = None
    model_used = None
    for model in _model_chain():
        try:
            response = client.models.generate_content(
                model=model,
                contents=[prompt, genai_types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")],
                config=genai_types.GenerateContentConfig(temperature=0.2, response_mime_type="application/json"),
            )
            text = response.text or ""
            model_used = model
            break
        except Exception as exc:
            if _is_rate_limited(exc):
                last_exc = exc
                continue
            return _fallback(f"API call failed: {exc}")
    else:
        return _fallback(f"All models rate-limited: {last_exc}")

    text = _strip_json_fence(text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return _fallback("response was not valid JSON")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return _fallback("response was not valid JSON")
    if not isinstance(parsed, dict):
        return _fallback("response was not a JSON object")

    result = _coerce(parsed)
    result["model_used"] = model_used
    result["_hinted"] = True
    return result


# ───────────────────────────────────────────────────────────────────────────
# OPTIMIZATION PIPELINE - preprocess / triage / confidence-gated critique
# ───────────────────────────────────────────────────────────────────────────

def preprocess_image(image: Image.Image) -> Image.Image:
    """Resize to 1280px max dimension to cut token usage 50–75%."""
    MAX = 1280
    w, h = image.size
    if max(w, h) > MAX:
        scale = MAX / max(w, h)
        image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    if image.mode != "RGB":
        image = image.convert("RGB")
    return image


def triage_classify(image: Image.Image, api_key: Optional[str] = None) -> Dict[str, Any]:
    """Quick top-3 classification using TRIAGE_PROMPT. Returns {"top_3": [...]}."""
    client = _client(api_key=api_key)
    if client is None:
        return {"top_3": []}

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    buf.seek(0)

    from google.genai import types as genai_types
    last_exc = None
    for model in _model_chain():
        try:
            response = client.models.generate_content(
                model=model,
                contents=[
                    TRIAGE_PROMPT,
                    genai_types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"),
                ],
                config=genai_types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            text = _strip_json_fence(response.text or "")
            parsed = json.loads(text)
            top3 = parsed.get("top_3", parsed.get("categories", []))
            if isinstance(top3, list):
                return {"top_3": [c for c in top3 if c in CATEGORY_LABELS][:3]}
            return {"top_3": []}
        except Exception as exc:
            if _is_rate_limited(exc):
                last_exc = exc
                continue
            return {"top_3": []}
    return {"top_3": []}


def confidence_gated_analyze(
    image: Image.Image,
    _unused_ctx: Dict[str, Any],
    primary: Dict[str, Any],
    user_context: str = "",
    threshold: float = 0.80,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run self-critique only when confidence is below threshold.
    Returns {"result": dict, "path": str, "tokens_estimate": int}.
    """
    confidence = float(primary.get("confidence", 1.0))
    if confidence >= threshold:
        return {"result": primary, "path": "direct", "tokens_estimate": 0}

    client = _client(api_key=api_key)
    if client is None:
        return {"result": primary, "path": "direct", "tokens_estimate": 0}

    critique_prompt = CRITIQUE_PROMPT_TEMPLATE.format(
        original_category=primary.get("category", ""),
        original_confidence=confidence,
        original_reasoning=" ".join(primary.get("reasoning_steps", [])),
        original_evidence=", ".join(primary.get("evidence", [])),
    )
    if user_context:
        critique_prompt += f"\n\nUser context:\n{user_context}"

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    buf.seek(0)

    from google.genai import types as genai_types
    for model in _model_chain():
        try:
            response = client.models.generate_content(
                model=model,
                contents=[
                    critique_prompt,
                    genai_types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"),
                ],
                config=genai_types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            text = _strip_json_fence(response.text or "")
            parsed = json.loads(text)
            if not parsed.get("agrees", True) and parsed.get("alternative_category"):
                alt_cat = parsed["alternative_category"]
                alt_conf = float(parsed.get("alternative_confidence") or confidence)
                if alt_cat in CATEGORY_LABELS and alt_conf > confidence:
                    updated = dict(primary)
                    updated["category"] = alt_cat
                    updated["category_label"] = CATEGORY_LABELS[alt_cat]
                    updated["confidence"] = alt_conf
                    updated["critique_note"] = parsed.get("reasoning", "")
                    return {"result": updated, "path": "critique_override", "tokens_estimate": 500}
            return {"result": primary, "path": "critique_agree", "tokens_estimate": 500}
        except Exception as exc:
            if _is_rate_limited(exc):
                continue
            break
    return {"result": primary, "path": "critique_failed", "tokens_estimate": 0}


# ───────────────────────────────────────────────────────────────────────────
# PROMPT ANALYZER - Live dashboard parsing
# ───────────────────────────────────────────────────────────────────────────

_GROUP_MAP: Dict[str, str] = {
    "traced_carbon": "traced",
    "traced_indentation": "traced",
    "traced_projection": "traced",
    "addition_insertion": "alteration",
    "addition_interlineation": "alteration",
    "erasure_chemical": "alteration",
    "erasure_mechanical": "alteration",
    "digital_cut_paste": "digital",
    "digital_desktop": "digital",
    "digital_scanned": "digital",
    "obliteration_ink": "obliteration",
    "obliteration_whiteout": "obliteration",
    "sympathetic_indented": "sympathetic",
    "sympathetic_special": "sympathetic",
    "currency_analysis": "currency",
    "no_forgery_detected": "fallback",
    "not_a_document": "fallback",
    "other": "fallback",
}


def _extract_category_blocks(prompt: str) -> Dict[str, str]:
    codes = list(_GROUP_MAP.keys())
    pattern = re.compile(
        r"^\s{2,}(" + "|".join(re.escape(c) for c in codes) + r")\s+-",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(prompt))
    blocks: Dict[str, str] = {c: "" for c in codes}
    for i, m in enumerate(matches):
        code = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(prompt)
        block = prompt[start:end]
        for terminator in [
            "\n═══════════════════════",
            "\nIGNORE these",
            "\nREASONING - work",
            "\nCONFIDENCE SCALE",
            "\nOUTPUT - return",
            "\nCRITICAL RULES:",
        ]:
            idx = block.find(terminator)
            if idx > 0:
                block = block[:idx]
        blocks[code] = block.strip()
    return blocks


def _prompt_word_count(text: str) -> int:
    cleaned = re.sub(r"\b[a-z]+_[a-z_]+\b", "", text)
    return len([w for w in cleaned.split() if any(c.isalpha() for c in w)])


def _extract_indicators(block: str) -> list[str]:
    indicators: list[str] = []
    for m in re.finditer(r"-\s+([A-Z][A-Z0-9 /\-]+(?:\s\([^)]+\))?)\s*[:-]", block):
        indicators.append(m.group(1).strip().rstrip(":"))
    look_for = re.search(r"Look for:\s*([^.\n]+)", block, re.IGNORECASE)
    if look_for and not indicators:
        for piece in look_for.group(1).split(","):
            p = piece.strip().rstrip(".")
            if p and len(p) < 80:
                indicators.append(p)
    seen = set()
    out = []
    for x in indicators:
        key = x.lower()
        if key not in seen:
            seen.add(key)
            out.append(x)
    return out[:10]


def _extract_distinctions(block: str) -> list[Dict[str, str]]:
    out = []
    pattern = re.compile(
        r"DISTINCTION\s+from\s+([a-z]+_[a-z_]+)([^:]*?:)?\s*(.+?)(?=\n\s*[⚠\n]|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern.finditer(block):
        target = m.group(1).strip()
        reason = m.group(3).strip()
        if target in _GROUP_MAP:
            out.append({"target": target, "reason": reason[:300]})
    return out


def _detail_label(words: int) -> str:
    if words >= 250: return "VERY HIGH"
    if words >= 130: return "HIGH"
    if words >= 60:  return "MEDIUM"
    if words >= 25:  return "LOW"
    return "VERY LOW"


def _extract_branching_rules(prompt: str) -> list[str]:
    rules: list[str] = []
    m = re.search(r"CRITICAL BRANCHING RULE.*?═══", prompt, re.DOTALL)
    if m:
        rules.append("CRITICAL BRANCHING RULE: " + re.sub(r"\s+", " ", m.group(0).split("═══")[0]).strip())
    for m in re.finditer(r"⚠\s+([A-Z][A-Z\s/]+RULE):\s+([^\n]+)", prompt):
        rules.append(f"{m.group(1).strip()}: {m.group(2).strip()}")
    return rules[:10]


def _extract_user_variables(source: str) -> list[Dict[str, str]]:
    influence = {
        "document_type": "Activates document-specific rules (bank check rule, ID security checks). Strong nudge toward category-relevant indicators.",
        "suspicion_reason": "Free text up to 300 chars - anchors classification with user keywords. Prompt warns model to verify against image.",
        "area_of_concern": "Directs attention to a region (signature, date field). Biases toward forgery types common to that area.",
        "image_source": "phone / scan / screenshot. Screenshots → digital_desktop more likely. Phone photos → physical forgeries more likely.",
        "is_forged_belief": "User's belief. Prompt explicitly tells the model NOT to be pressured.",
        "shot_type": "Close-up vs full document. Affects which evidence is visible (micro-tremors vs layout).",
        "lighting": "Critical for sympathetic_indented (raking) and erasure detection (oblique sheen).",
        "physical_clues": "STRONGEST single bias - 16 specific clue options each map to a category target.",
    }
    desc = {
        "document_type": "Document type (passport, check, contract, ID, etc.) chosen from a fixed list.",
        "suspicion_reason": "Free-text description of why the user suspects forgery.",
        "area_of_concern": "Where to focus the analysis.",
        "image_source": "Phone photo / scan / screenshot / not sure.",
        "is_forged_belief": "User's belief about authenticity.",
        "shot_type": "Close-up vs full document.",
        "lighting": "Lighting condition (natural / raking / bright).",
        "physical_clues": "Specific clue user thinks they observed (16 options).",
    }
    out = []
    for name in influence:
        out.append({
            "name": name,
            "description": desc[name],
            "influence": influence[name],
        })
    return out


def analyze_prompts() -> Dict[str, Any]:
    system = SYSTEM_PROMPT
    blocks = _extract_category_blocks(system)
    categories: list[Dict[str, Any]] = []
    overlaps: list[Dict[str, Any]] = []
    for code, block in blocks.items():
        words = _prompt_word_count(block) if block else 0
        indicators = _extract_indicators(block) if block else []
        distinctions = _extract_distinctions(block) if block else []
        categories.append({
            "id": code,
            "label": CATEGORY_LABELS.get(code, code),
            "group": _GROUP_MAP.get(code, "fallback"),
            "word_count": words,
            "detail_level": _detail_label(words),
            "indicators": indicators,
            "distinctions": distinctions,
            "first_line": block.split("\n", 1)[0][:200] if block else "",
        })
        for d in distinctions:
            overlaps.append({
                "source": code,
                "target": d["target"],
                "reason": d["reason"],
                "from_prompt": True,
            })
    semantic = [
        ("traced_carbon", "traced_indentation", "Both hand-drawn with hesitation/tremor; carbon has residue, indentation has groove."),
        ("traced_carbon", "traced_projection", "Both show uniform line weight from following a guide."),
        ("traced_indentation", "traced_projection", "Both hand-drawn from a visual reference."),
        ("sympathetic_indented", "traced_indentation", "Both involve grooves; sympathetic has grooves WITHOUT ink, traced has grooves WITH ink. Not explicitly distinguished in prompt."),
        ("erasure_chemical", "obliteration_ink", "Both can show smudges/halos. Erasure smudge at edge of blank; obliteration covers text."),
        ("obliteration_ink", "obliteration_whiteout", "Both cover text. Minimal prompt detail (≤5 words each)."),
    ]
    existing = {(o["source"], o["target"]) for o in overlaps} | {(o["target"], o["source"]) for o in overlaps}
    for src, tgt, reason in semantic:
        if (src, tgt) not in existing and (tgt, src) not in existing:
            overlaps.append({"source": src, "target": tgt, "reason": reason, "from_prompt": False})
    aux_prompts = [
        {"name": "SYSTEM_PROMPT", "purpose": "Main 18-category classification (full pass)", "word_count": _prompt_word_count(system), "char_count": len(system)},
        {"name": "TRIAGE_PROMPT", "purpose": "Stage 1 quick top-3 classification (~$0.00005)", "word_count": _prompt_word_count(TRIAGE_PROMPT), "char_count": len(TRIAGE_PROMPT)},
        {"name": "DETAILED_PROMPT_TEMPLATE", "purpose": "Stage 2 narrowed prompt (currently unused - kept for experiments)", "word_count": _prompt_word_count(DETAILED_PROMPT_TEMPLATE), "char_count": len(DETAILED_PROMPT_TEMPLATE)},
        {"name": "CRITIQUE_PROMPT_TEMPLATE", "purpose": "Stage 3 self-critique when confidence < 0.80", "word_count": _prompt_word_count(CRITIQUE_PROMPT_TEMPLATE), "char_count": len(CRITIQUE_PROMPT_TEMPLATE)},
    ]
    rules = _extract_branching_rules(system)
    variables = _extract_user_variables(system)
    return {
        "system_prompt": {
            "total_words": _prompt_word_count(system),
            "total_chars": len(system),
        },
        "categories": sorted(categories, key=lambda c: -c["word_count"]),
        "overlaps": overlaps,
        "aux_prompts": aux_prompts,
        "rules": rules,
        "variables": variables,
        "groups": {
            "traced": "#e74c3c",
            "alteration": "#f39c12",
            "digital": "#5b8def",
            "obliteration": "#9b59b6",
            "sympathetic": "#1abc9c",
            "currency": "#95a5a6",
            "fallback": "#666",
        },
    }
