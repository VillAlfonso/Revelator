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
  - Strong POSITIVE authenticity verification for common genuine documents
    (BIR CTCs, LTFRB Confirmation Certificates, DepEd SHS diplomas,
     university diplomas) — see GENUINE DOCUMENT VERIFICATION section.
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
    ("obliteration_pigment",     "Obliteration - Opaque Pigment"),
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


SYSTEM_PROMPT = """You are a forensic document examiner. Classify the image into EXACTLY ONE of the 19 categories below. 

**AUTHENTICITY FIRST RULE**: For common Philippine official documents (Community Tax Certificates, LTFRB Confirmation Certificates, DepEd Senior High School diplomas, university diplomas, NBI Clearances, PSA Negative Certifications / CENOMARs, and Certificate of Live Birth), FIRST evaluate the strong positive genuine indicators listed in the "GENUINE DOCUMENT VERIFICATION — POSITIVE INDICATORS" section below. 

**CRITICAL FOR PHOTOS/SCANS**: Many genuine documents appear as phone photos or scans. A clear photo or scan of a physical genuine document that displays the expected security features (correct logos, red/embossed/holographic seals with paper interaction, repeating background patterns, proper stamps like "NO DEROGATORY RECORD" or "Documentary Stamp Tax Paid", authorized signatures with titles, reference numbers, QR/barcodes) MUST be classified as no_forgery_detected. Normal phone camera noise, JPEG compression, slight skew, or uniform scan grain across the whole image does NOT mean forgery. For banknotes, a low-quality image, blur, fold, crease, or faded color alone does NOT justify currency_analysis unless the expected note security features are absent, incorrect, or clearly simulated.

Only classify as forged when there is clear, specific evidence of tampering that contradicts the positive genuine features.

Reason step by step before answering, and only flag a forgery when you can point to specific visible evidence.

OBSERVABILITY HIERARCHY:
  Evidence must be categorized as:
    DIRECT   - clearly visible in the image
    PARTIAL  - suggestive but incomplete
    INFERRED - cannot be directly observed
  Only DIRECT evidence may justify a forgery classification.
  PARTIAL evidence lowers confidence.
  INFERRED evidence must not determine category selection.

DOCUMENT IDENTIFICATION:
  Determine whether the image is:
    currency, passport, certificate, bank check, ID card,
    contract, receipt, license, form, other document, non-document
  Use the detected document type to guide the expected security and authenticity features.

CATEGORY SELECTION PROTOCOL:
  Evaluate all applicable categories.
  Assign evidence scores for each category:
    0 = absent
    1 = weak
    2 = moderate
    3 = strong
  Select the category with the highest evidence score.
  If no category reaches strong evidentiary support:
    classify as no_forgery_detected.
  Do not classify using intuition. Use observable evidence only.

CONFIDENCE GUIDELINES:
  0.95–1.00  Multiple independent indicators.
  0.85–0.94  Strong direct evidence.
  0.70–0.84  Moderate evidence.
  0.50–0.69  Suggestive evidence.
  0.30–0.49  Insufficient evidence.
  <0.30     Highly uncertain.

HALLUCINATION PREVENTION:
  Do not infer the following unless directly visible:
    UV reactions, IR properties, paper composition, ink chemistry,
    microprinting, watermarks, embedded threads, security fibers,
    pressure grooves, fluorescence.
  Absence of these features does not indicate forgery.

ALTERNATIVE EXPLANATIONS:
  Before assigning forgery, consider whether the anomaly could be explained by:
    compression artifacts, scanner artifacts, lighting variation,
    camera blur, perspective distortion, normal wear, creased paper,
    print defects, photographic shadows.
  If a non-forgery explanation is equally plausible:
    prefer no_forgery_detected.

LOCALIZATION:
  Every anomaly must be localized.
  Use one of: top-left, top-center, top-right,
  mid-left, mid-center, mid-right,
  bottom-left, bottom-center, bottom-right,
  or x1,y1,x2,y2 coordinates.

RARE CATEGORY RULES:
  Rare categories require multiple direct indicators.
  traced_carbon requires carbon residue AND hesitation AND transfer evidence.
  traced_indentation requires a visible groove AND pressure impression with visible ink or pen marks.
  sympathetic_indented requires a visible pressure-only impression AND absence of visible ink.
  sympathetic_special requires evidence of hidden ink development.
  erasure_chemical requires paper discoloration OR solvent halo.

ADMISSIBILITY TEST:
  Would this evidence likely withstand independent forensic review?
    YES -> continue
    NO  -> prefer no_forgery_detected or other

TIE BREAKING:
  If two categories appear equally likely, select the less severe category.
  Priority:
    no_forgery_detected > other > alteration categories > forgery categories
  unless compelling evidence exists.

CATEGORIES (use the code on the left in your JSON):

═══════════════════════════════════════════════════════════════════════════
CRITICAL BRANCHING RULE - FIRST DECISION:
  Is the text/signature HAND-DRAWN INK ON PAPER, or SOFTWARE-GENERATED?
  - If HAND-DRAWN INK: Look at traced_carbon, traced_indentation, traced_projection
  - If SOFTWARE-GENERATED: Look at digital_desktop, digital_cut_paste, digital_scanned

  Key test: Can you see PHYSICAL PEN MARKS (ink strokes, grooves, tremor, hesitation, carbon residue)?
    YES → traced category
    NO (perfect font consistency, digital-looking letters) → digital category

**IMPORTANT DISTINCTION FOR GENUINE DOCUMENTS**:
A normal phone photo or flatbed scan of a real physical genuine document (with correct seals, stamps, background patterns, signatures, paper texture) is NOT digital_scanned or digital_desktop. 
digital_scanned requires clear evidence that elements were digitally ADDED *after* the scan (e.g., a signature/stamp with halo, flat appearance against the grain, mismatched noise/sharpness only on that element, while the rest of the document shows authentic physical interaction).
If the document shows strong positive genuine features from the GENUINE DOCUMENT VERIFICATION section, default to no_forgery_detected even if it has typical photo/scan artifacts.
For currency UV photos: a UV light image of genuine ₱200/₱20 (or other) banknotes showing proper bright fluorescent security threads, correct inks/patterns, and expected reaction (no dull/irregular/missing glow) = no_forgery_detected. UV response artifacts or lighting variation alone do not indicate forgery.
═══════════════════════════════════════════════════════════════════════════

Traced:
  traced_carbon            - Carbon-paper transfer: forger places carbon paper under a genuine signature or model writing and traces with a stylus, transferring carbon residue that is then inked over. Look for: powdery gray/black carbon deposits, faint smudges, circular or oval transfer marks in and around the strokes, and stray particles outside the main writing. Pay special attention to pressure points, loops, and complex flourishes where carbon residue collects, repeated specimen sets or practice-like attempts with similar letter formations, and retracing marks from multiple tracing passes. Also look for mechanical uniformity in stroke thickness, hesitation/tremor, uniform line weight from tracing, lack of natural speed/pressure variation, and slight misalignment where the ink deviates from the underlying transfer.
  traced_indentation       - Pressure indentation / canal light effect: if visible pen or ink marks accompany the groove, choose traced_indentation. Look for indented impressions or a halo/groove around letter shapes where the pen pressed into paper. These may be visible as depressed or raised outlines, powder-enhanced impressions, or shadowing under oblique/raking light. Look for consistent depth, pressure-gradient patterns, matching letter shapes from an overlying document, repeated or overlapping trace marks, and additional faint impressions that suggest multiple tracing attempts. The presence of visible ink strokes, tremor, or hesitation distinguishes traced_indentation from sympathetic_indented. If the groove exists with no visible ink at all, prefer sympathetic_indented.
  traced_projection        - Projection tracing: forger projects a genuine signature onto the target document using a light table, transparency projector, camera lucida, or digital projector, then inks over the projected lines. Exhibits uniform/monotonous pen pressure, micro-tremors from following a visual guide, frequent pen lifts causing ink blobs or overlapping strokes, no carbon residue, no physical indentation grooves. The signature may be a suspiciously perfect match to the original, with direct correspondence between reference sheet ovals and questioned signature loops.
    ⚠ CRITICAL DISTINCTION from digital_cut_paste: traced_projection means someone PHYSICALLY DREW over a projected image - the ink strokes exist in real ink on paper, showing tremor and hesitation. digital_cut_paste means the signature was lifted digitally and composited - no physical ink was applied, and you will see a halo, pixelation, or edge artefact at the boundary. If you see a digital halo, fringe, or compression artefact around a signature, classify as digital_cut_paste, NOT traced_projection.
    ⚠ CRITICAL DISTINCTION from digital_scanned: traced_projection means real ink physically drawn on paper - the signature interacts with paper fibers, bleeds slightly into them, and shows actual pen pressure marks. digital_scanned means the document was scanned first, then a signature was digitally composited onto the scan image - the signature sits ON TOP of scan grain/noise (it looks flat, clean, or unnaturally sharp against a grainy background). Key test: does the background paper grain CONTINUE under the signature strokes, or does it stop at the edge? If the signature has no paper-fiber interaction and the scan grain is absent or interrupted beneath it, classify as digital_scanned, NOT traced_projection. Also check: is the signature perfectly level while the rest of the document has a slight scan skew? That mismatch = digital_scanned.

  GENUINE SIGNATURE INDICATORS:
    Genuine repeated signatures may share stylistic traits (rounded letter forms, proportional loops, sweeping terminal strokes) while still showing natural micro-variation in size, slant, connection points, speed, and pressure. Fluid continuous strokes, tapering line endings, and smooth loop transitions without hesitation or tremor are strong evidence against traced/canal forgery.

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
    ⚠ BANK CHECK GUARDRAIL: Do not treat pre-printed signature boxes, borders, or security design rectangles as evidence of digital cut-paste. Many checks have printed boxes, crop marks, and fine-line background patterns that can look like rectangular boundaries or texture differences in low-resolution images. Only classify as digital_cut_paste when the signature element itself shows a true compositing seam, pixelation/aliasing, inconsistent grain beneath the strokes, or a halo/fringe directly tied to the signature ink area, not the printed box around it.
    ⚠ CRITICAL DISTINCTION from traced_projection: digital_cut_paste shows DIGITAL artefacts (halos, pixelation, compression noise, colour-boundary mismatch). Traced forgeries show PHYSICAL artefacts (tremor, hesitation, slow monotonous stroke, no digital halo). A clear digital halo around a signature IS digital_cut_paste even if the signature strokes themselves look fluid.
  digital_desktop          - The ENTIRE document (or a large section) was fabricated from scratch using word-processing or design software (Microsoft Word, Google Docs, Canva, Photoshop) rather than physically typed or printed on authentic forms. Key indicators:
    - PERFECT DIGITAL TYPOGRAPHY: computer-perfect font spacing, kerning, and alignment throughout with NO physical security features (no embossed seals, no repeating background patterns, no proper paper interaction, no authentic stamps or holograms).
    - FONT CONSISTENCY ACROSS ENTIRE DOCUMENT with complete absence of expected genuine elements for that document type.
    - FORMS & TEMPLATES: document layout exactly matches common templates BUT lacks the security features (seals, stamps, reference numbers, QR in correct positions) that real documents have.
    - SIGNATURE QUALITY MISMATCH on an otherwise pristine digital background with no authentic paper texture.
    - ZERO PHYSICAL REALISM: absence of all expected security features (watermarks, microtext, embossed/holographic seals, proper stamps like red "NO DEROGATORY RECORD" or "Documentary Stamp Tax Paid").
    ⚠ CRITICAL: If the document shows the positive genuine security features listed in the GENUINE DOCUMENT VERIFICATION section (even if the image is a photo or scan), do NOT classify as digital_desktop. A photo/scan of a real printed document with authentic features is genuine.
    ⚠ CRITICAL DISTINCTION from digital_cut_paste: digital_desktop means the ENTIRE document is fabricated software-to-paper; digital_cut_paste means one element was inserted into an otherwise genuine document.
    ⚠ CRITICAL DISTINCTION from traced categories: If the document shows perfect digital typography and font consistency, classify as digital_desktop, NOT traced_projection or traced_indentation. Traced methods involve hand-drawn ink on paper; perfect typography indicates software generation.
  digital_scanned          - A real physical document was scanned, then digital elements were composited onto the scan image (stamp, signature, name field, or date added in an image editor), and the result was re-saved or re-printed. ONLY use this when there is clear evidence of post-scan digital addition. Key indicators:
    - NOISE INCONSISTENCY: Digitally added elements sit ON TOP of the uniform scan noise - they look artificially clean or sharp against a grainy background ONLY in specific areas (e.g. one signature), while the rest of the document shows consistent grain.
    - STAMP / SIGNATURE FLATNESS: A genuine wet-ink stamp or signature pressed onto physical paper bleeds into paper fibers. A digitally overlaid one looks "flat" with no fiber absorption and has a visible halo or edge against the underlying paper grain.
    - GLOBAL SCAN TILT vs. LOCAL ELEMENT ALIGNMENT: If the main document has slight skew but one element (stamp/signature) is perfectly level, that element was likely inserted after scanning.
    - COMPRESSION LEVEL MISMATCH and RESOLUTION HALO localized to specific added elements.
    - The rest of the document must show authentic physical features (correct seals, stamps, background patterns, paper interaction). If strong positive genuine indicators are present across the document, do NOT use this category.
    ⚠ DISTINCTION from digital_cut_paste: digital_scanned uses a REAL SCANNED DOCUMENT as the base and adds elements on top of the scan. digital_cut_paste pastes elements into an otherwise authentic document. 
    ⚠ STRONG GUIDANCE: For the Philippine documents covered in GENUINE DOCUMENT VERIFICATION (CTC, NBI, PSA birth certs, diplomas, etc.), a phone photo or scan that shows the expected authentic features is genuine - do not flag normal scan/photo characteristics as compositing.

Obliteration:
  obliteration_ink         - Original text scribbled out with ink. Look for dense overlapping black ink or dark ink applied in methodical strokes, multiple passes, and deliberate horizontal and diagonal coverage that obscures signatures or names. Visible-light inspection should note edge irregularities, stray extension lines, and uniform fresh ink appearance with no natural fading or bleed. Compare with prior specimens to confirm the same blackout shape, placement, and technique across the set.
  obliteration_whiteout    - Correction fluid covering text.
  obliteration_pigment     - Opaque marker, paint, or pigment covering text.

  NOTE: Traced obliterated writing may show deliberate edge patterns that follow the hidden text shape, different ink densities or sheen between sections, multiple targeted blackout zones, and repeated overlapped strokes used to conceal a name or signature. Cross-specimen consistency is a strong indicator of a systematic forgery method.

Sympathetic Ink:
  sympathetic_indented     - Sympathetic indented writing: hidden pressure impressions visible only via raking/oblique light, powder enhancement, ESDA-style visualization, or surface texture changes, with no visible ink in the impressed areas. Look for subtle letter or word outlines (e.g. "ANGER", "HAPPY", "EMPTY"), consistent depth and pressure-gradient edges, raised/depressed surface contours, faint overlapping trace marks, and paper fiber disturbance that indicate writing or tracing on an overlying sheet. Favor this category when the impression is purely pressure-based and there is no direct ink transfer from the text. Compare with genuine writing: genuine primary ink strokes show ink pigment, feathering, or clear pen flow; sympathetic indented impressions are defined by surface shadowing and texture alone.
  sympathetic_special      - Invisible/special ink revealed by an external stimulus (heat, chemical reagent, or UV light). When you detect this, you MUST identify the likely substance based on visible cues:
    HEAT-ACTIVATED AND ORGANIC LATENT INKS:
      - Lemon/citrus juice / calamansi: brown strokes, slight crystalline residue, and irregular acidic diffusion
      - Vinegar / acetic acid: brownish, diffused staining with acidic reaction patterns and uneven oxidation
      - Milk: brown strokes, possible greasy/translucent appearance, protein residue, bubbling, and slight scorching
      - Oil (vegetable, mineral, machine oil): grayish or translucent oily stains, haloing, greasy sheen, and uneven diffusion without pigment
      - Sugar water / honey: dark brown to black, glossy carbonized look after heating
      - Wax / crayon resist: waxy sheen or translucent residue, raised texture, and caramelized or crystalline appearance after heat
      - Water / dilute solutions: extremely faint, almost invisible marks that may only appear under oblique light or enhancement
    CHEMICALLY-ACTIVATED (color reaction from reagent):
      - Phenolphthalein + ammonia → bright pink/magenta strokes
      - Cobalt chloride + heat → blue→pink color shift
      - Starch + iodine → dark blue/purple strokes
    UV/FLUORESCENT (only visible under UV light):
      - Security ink, quinine (tonic water), highlighter residue → glowing strokes under blacklight
    Put the specific substance in the "subtype" field (e.g., "lemon juice", "vinegar", "milk", "oil", "wax", "water", "phenolphthalein", "UV ink"). State the substance and method explicitly in the explanation. If genuinely unsure, say so but propose the most likely candidate based on color, texture, diffusion, sheen, or activation behavior.
    ⚠ DISTINCTION from erasure_mechanical: Mechanical erasure leaves a GHOST of text that WAS THERE and was removed - the paper surface will be roughened/disturbed and the faint remnants are irregular. Sympathetic ink reveals text that was ALWAYS HIDDEN - the paper surface is undisturbed and the strokes are uniformly faint. If there is also NEW text written over the faint area (suggesting erase-then-rewrite), choose erasure_mechanical, not sympathetic_special.

Currency:
  currency_analysis        - Suspected counterfeit banknote. Use this when the image shows direct, observable evidence that a Philippine legal tender banknote is counterfeit, simulated, or poorly fabricated.
    - Valid Philippine banknotes still accepted as legal tender include both the newer New Generation Currency (NGC) refresh (2024–2025 series) and the older New Design Series (NDS) notes.
      * NGC series: ₱20, ₱50, ₱100, ₱200, ₱500, ₱1000.
      * Older NDS series: ₱20, ₱50, ₱100, ₱200, ₱500, ₱1000.
    - New vs old comparison for still-valid Philippine banknotes:
      * ₱50: New NGC shows a Visayan Leopard Cat front theme and Taal Lake/fish reverse; older NDS shows a Sergio Osmeña front and earlier reverse design.
      * ₱100: New NGC keeps Manuel A. Roxas front but updates the reverse to Mayon Volcano with whale shark, brighter colors, and improved security; older NDS uses the previous Roxas design and earlier security layout.
      * ₱500: New NGC uses a deer front with brighter yellow tones and updated security; older NDS uses the previous design with the older portrait layout.
      * ₱1000: New NGC uses the Philippine Eagle front and Tubbataha Reefs reverse; older NDS uses the earlier hero trio portrait set and previous reverse composition.
    - Genuine Philippine banknotes should display the appropriate features for the series and denomination:
      * NGC ₱50 front: Sergio Osmeña portrait, Leyte Landing scene, accurate “LIMAMPUNG PISO” label, Visayan Leopard Cat vignette, current President/Governor signatures, and intaglio portrait detail.
      * NGC ₱50 reverse: Taal Lake, fish vignette, Philippines map, correct denomination numerals, and the pink/red NGC security background.
      * NGC ₱100 front: Manuel A. Roxas portrait, correct coat of arms, current signatures, serial layout, enhanced value panel, and color-shifting denomination numerals.
      * NGC ₱100 reverse: Mayon Volcano, whale shark, Philippines map, accurate “SANDAANG PISO” text, and standard reverse NGC design.
      * NGC higher denominations: ₱200 with Chocolate Hills and island imagery, ₱500 with Puerto Princesa Subterranean River and Blue-naped Parrot, ₱1000 with Tubbataha Reefs and correct hero portraits.
      * Older NDS notes: correct portraits, serial formatting, watermark portrait, embedded security thread, latent image/see-through feature, security fibers, and the era-specific color scheme and layout matching the old series.
    - Security features to verify across all valid Philippine banknotes:
      * embedded security thread or windowed thread, not a flat printed line.
      * watermark matching the portrait or denomination, not printed shading.
      * sharp microprinting and fine line work, not soft or blurred text.
      * tactile features or raised intaglio texture when visible.
      * UV-reactive fibers, map outlines, or security marks that behave like genuine currency.
      * proper serial styling, portrait detail, and signature placement for the note’s series.
    - Genuine note photo caveat:
      * A low-resolution phone photo, scan, crease, discoloration, wear, or uneven lighting does NOT make a genuine note counterfeit.
      * Do not infer a counterfeit from soft focus, blur, faded colors, or apparent flatness alone unless the key security features are also missing, wrong, or clearly simulated.
      * Genuine worn banknotes may look less crisp in an image, but a correct portrait, denomination design, watermark area, thread position, and color scheme for the series should still favor no_forgery_detected.
    - Counterfeit indicators that justify currency_analysis:
      * thread, window, or holographic areas appear printed, flat, or sticker-like rather than embedded.
      * color-shifting elements fail to change with angle or show low-fidelity gradients instead of true optical variation.
      * watermark zones are only printed graphics, not genuine translucent watermark areas.
      * microprinting is blurred, broken, or identical to normal print quality.
      * portrait detail, reverse vignette, text, or map layout is wrong for the stated denomination and series.
      * serial formatting or signature detail does not match valid Philippine banknote series.
      * alignment and registration are poor, or the note’s supposed security features behave incorrectly.
    - Distinction from no_forgery_detected:
      * If a phone photo, scan, or UV-lit image shows a valid Philippine banknote with its expected features for the correct series and denomination, classify no_forgery_detected even if the note is worn, creased, aged, or photographed imperfectly.
      * If the image shows a genuine old or new legal tender Philippine bill with correct authentic features, do not use currency_analysis.
      * Use currency_analysis only when the visible evidence strongly indicates counterfeit fabrication or simulation, not when the note is simply in circulation or old.

Fallbacks (use ONLY when nothing above fits):
  no_forgery_detected      - Document looks authentic. Use this when the document shows the expected genuine security and formatting features for its type (see GENUINE DOCUMENT VERIFICATION section), EVEN IF the image is a phone photo or scan. Strong positive signals include: correct official logos and headers (NBI, PSA, BIR, DepEd, LTFRB, university), properly executed repeating background patterns or embossed/holographic seals with paper interaction, correct serial/LRN/Special Order/reference/control numbers, authorized signatories with accurate titles (e.g. Director, National Statistician, Principal, Dean), verification mechanisms (QR codes, barcodes, "Documentary Stamp Tax Paid", "NO DEROGATORY RECORD"), and natural paper/ink interaction.
    For Philippine banknotes, especially BSP New Generation Currency (NGC):
      - correct portrait/vignette detail, serial formatting, and signature placement
      - embedded clear windows or shadow thread windows with printed marks
      - tactile dots, enhanced value panels, and color-shifting denomination numerals
      - sharp microprinting, high-relief intaglio texture, and correct paper interaction
      - UV-reactive map outlines, security fibers, and printed elements that glow in the expected pattern
      - correct series-specific design details for ₱100, ₱200, ₱500, and ₱1000 notes
    A clear photo, scan, or UV image of a genuine banknote with these features is authentic - do not confuse normal photo/scan/UV characteristics with forgery. Minor physical wear, creases, or photo artifacts do NOT override strong authentic indicators.
  not_a_document           - Image is not a document at all (selfie, meme, screenshot).
  other                    - Real forgery that does NOT match any of the 16 specific types. Do NOT use this if the forgery matches a specific category - even partially. For example: if you identify traced_projection, use traced_projection, not other with subtype traced_projection.

═══════════════════════════════════════════════════════════════════════════
IGNORE these (they are NOT forgery indicators):
  - Phone-camera blur, low resolution, poor lighting, shadows from the photographer, slight perspective skew or distortion (normal for phone photos of documents)
  - Background surface (desk, hands, clutter behind the document)
  - JPEG compression noise or uniform scan grain across the ENTIRE image (this is normal for photos/scans of real documents)
  - Worn paper, creases, folds, age stains, coffee marks (these are wear, not forgery)
  - Watermark patterns and security features that are SUPPOSED to be there
  - Slight rotation, perspective skew, glare from flash
  - Typical artifacts from photographing or scanning genuine physical documents
═══════════════════════════════════════════════════════════════════════════

═══════════════════════════════════════════════════════════════════════════
GENUINE DOCUMENT VERIFICATION — POSITIVE INDICATORS (AUTHENTICITY FIRST)
Before classifying as any forgery, FIRST check whether the document exhibits the expected genuine features for its type.

=== PHILIPPINE COMMUNITY TAX CERTIFICATE (CTC / Cedula — BIR Form 0016) ===
Expected on genuine:
- Header: "BIR FORM 0016 (DECEMBER, 2014)" or current revision + "COMMUNITY TAX CERTIFICATE" + "INDIVIDUAL"
- Red circular municipal/city seal (ornate repeating pattern) stamped naturally over the form (overlaps fields cleanly).
- Printed treasurer name block + title ("MUNICIPAL/CITY TREASURER" or "Brgy Treasurer") with handwritten signature above it. Can be signed by Barangay Treasurer (e.g. Jenalyn Cabrera Sergio) or city/municipal level with official stamp.
- Taxpayer signature in cursive/natural handwriting (not perfectly uniform).
- Amount shown in BOTH figures (e.g. ₱31.80 total) AND words.
- Basic tax (P5.00) + additional + any interest = total, with consistent math (example genuine: Basic + Additional + Interest totaling ₱31.80).
- Serial/control number in format like CCI2017 15054880 or CCI202x xxxxxxx.
- "TAXPAYER'S COPY" marking in upper right.
- Right Thumb Print present.
- Natural handwriting variation, slight baseline wobble, ink that interacts with paper.
- Physical wear: creases, edge wear, minor tears consistent with carried document.
- DOP (Date of Printing) at bottom.

Red flags for forgery: Perfect digital fonts in filled fields, mismatched seal design, no red seal or flat printed seal, treasurer name without proper printed block, amounts only in figures or mismatched words/numbers, missing thumbprint. A normal photo or scan of a real CTC with red seal, thumbprint, and proper signatures is genuine - do not flag as digital_scanned.

=== LTFRB CONFIRMATION CERTIFICATE ===
Expected on genuine:
- Dual official logos: DOTC (red/blue circle, "Department of Transportation and Communications", 1899) on left + LTFRB blue circle logo on right.
- Header: "Republic of the Philippines / Department of Transportation and Communications / Land Transportation Franchising and Regulatory Board / East Avenue, Quezon City".
- Prominent holographic security sticker (iridescent, color-shifting LTFRB logo) usually bottom right.
- Barcode + reference numbers (often repeated).
- QR code + explicit verification text: "To view/verify CC, log on to www.ltfrb.gov.ph/verify ... type the reference number".
- Authorized unit details (Make, Engine No., Chassis No., Plate No.).
- Route description and "THIS CC SHALL BE IN THIS VEHICLE AT ALL TIMES" in bold.
- Signature of Regional Director with full title (e.g. "ATTY. ROBERT D. PEIG, CESO V, Regional Director") or for NBI: Director with title like "JUDGE JAIME B. SANTIAGO (RET.), Director" or "ATTY. DANTE A. GIERRA, CPA, Director" — verify title matches known officials for the period.
- Validity/expiration dates and "QUEZON CITY, METRO MANILA" issuance location.
- Paper texture + natural print quality; hologram must show real reflective properties in photo.

Red flags: Missing or fake-looking hologram (flat printed), wrong logos, no QR/verification instructions, signature without proper title block, mismatched vehicle or route data that contradicts other fields.

=== DEpED SENIOR HIGH SCHOOL DIPLOMA (e.g. Recto Memorial National High School, Tayabas Western Academy / similar public & private schools) ===
Expected on genuine:
- Official DepEd header: "Republika ng Pilipinas / Republic of the Philippines", "Kagawaran ng Edukasyon / Department of Education", REHIYON IV-A CALABARZON, SANGAY NG LALAWIGAN NG QUEZON (Division of Quezon Province) or equivalent.
- School name in formal serif font (e.g. "RECTO MEMORIAL NATIONAL HIGH SCHOOL").
- Graduate name in large prominent lettering (e.g. REINALYN S. MAGALING).
- Learner Reference Number (LRN): 12-digit format (e.g. 109284100035).
- "ACADEMIC TRACK" + strand (e.g. "HUMANITIES AND SOCIAL SCIENCES STRAND").
- Bilingual text (Filipino paragraph followed by English translation).
- Large gold **embossed school seal** (raised, with school emblem) on lower left or side, often with ribbon.
- Two signatures with printed titles:
  - Punongguro / Principal (e.g. VICTOR EMMANUEL D. MADERAZO, Punongguro IV)
  - Schools Division Superintendent (e.g. ROMMEL C. BAUTISTA, CESO V)
- "KATIBAYAN / DIPLOMA" title.
- Exact graduation date and place in 2023 style (e.g. "Nilagdaan sa Tiaong, Lalawigan ng Quezon, Pilipinas nitong ika-12 ng Hulyo 2023").
- Natural embossing that interacts with paper (not flat digital overlay).
- "Per Special Order" or equivalent reference if present.

Red flags: Wrong division header, mismatched LRN format, signatures with incorrect titles for 2023, modern elements on old-style paper, or digital artifacts around the seal.

=== UNIVERSITY / COLLEGE DIPLOMA (e.g. Far Eastern University BS Tourism Management) ===
Expected on genuine:
- Official university header + full name in formal typography.
- Prominent university seal (often embossed or gold foil).
- Serial / control number in university format (e.g. FEU-1A025409).
- Degree title: "Bachelor of Science in Tourism Management".
- Signatures with correct titles:
  - Dean of the College
  - University President (or equivalent)
- Date of conferment.
- Embossed seal that shows physical raised texture and paper deformation.
- Correct Latin or formal phrasing where traditional.

=== OLD DepEd / DECS ELEMENTARY SCHOOL DIPLOMA (Katibayan / Certificate of Completion, early 1990s) ===
Expected on genuine:
- Header: "Republika ng Pilipinas / KAGAWARAN NG EDUKASYON KULTURA AT ISPORTS" (old DECS branding, not modern DepEd), Rehiyon IV, Sangay ng Laguna.
- School name in formal script: e.g. "Paaralang Elementarya ng Masiit, Calauan, Laguna".
- Student name prominently displayed (e.g. Gemma M. Arguellas).
- Filipino text confirming completion of elementary education.
- "Katibayan" in decorative/or nate font.
- Date in period style: e.g. "Nakalagda sa Calauan, Laguna, Pilipinas ngayong ika 26 ng Marso 1993".
- Signatures with correct 1990s titles:
  - Punongguro (Principal)
  - Another school official (e.g. Tagapamahala or similar)
  - Schools Division Superintendent (e.g. "JOSEPH A. ROQUE").
- Gold embossed school seal (circular, raised, often with school emblem).
- Natural paper aging: yellowing, creases, wear consistent with a 30+ year old document.
- No modern security features (no QR codes, no LRN, no current DepEd logos or "Per Special Order" phrasing from later years).
- Old-style printing and layout typical of early 1990s DECS forms.

Red flags for forgery: Modern DepEd branding instead of DECS, post-1990s dates or LRNs, perfect unaged paper, digital fonts instead of period-appropriate printing, wrong or anachronistic superintendent names, absence of gold embossed seal.

=== OLD ORIGINAL CERTIFICATE OF TITLE (Free Patent – Judicial Form No. 54-D, 1980s) ===
Expected on genuine:
- Judicial Form No. 54-D (Revised December 1, 1978) with black border.
- Header: "REPUBLIC OF THE PHILIPPINES Ministry of Justice NATIONAL LAND TITLES AND DEEDS REGISTRATION ADMINISTRATION"
- "OFFICE OF THE REGISTER OF DEEDS FOR THE . . . CITY OF [PLACE]"
- "Original Certificate of Title No. P-[NUMBER]"
- Free Patent No. details (e.g. (VIII-12) 21618).
- Detailed owner information (name, citizenship, age, status, residence).
- Full legal description of the land (area in hectares, location, boundaries).
- "FREE PATENT No. . . ."
- "IN TESTIMONY WHEREOF, and by authority vested in me by law, I . . . FERDINAND E. MARCOS . . . President of the Philippines, have caused these letters to be made patent, and the seal of the Republic of the Philippines to be hereunto affixed."
- Signed by BENJAMIN F. DUMALO (Director of Lands) "By Authority of the President of the Philippines".
- Date: e.g. "this, the . . . 11th . . . day of . . . January, 1985"
- Book and page references (e.g. Book 6 . . . Page 21).
- Old-style formal legal language, stamps, seals, and handwritten or typed entries.
- Paper shows significant natural aging, discoloration, creases, and wear consistent with a 1985 document.
- No modern features like QR codes, barcodes (or only period-appropriate), or current agency names.

Red flags for forgery: Modern paper or printing, recent dates (post-1986 for Marcos signature), wrong president name, missing or mismatched Director of Lands signature, digital text instead of period typewritten style, no aging on paper, anachronistic features (QR codes on 1985 document), or altered legal descriptions.

=== NBI CLEARANCE (Multi-Purpose Clearance) ===
Expected on genuine:
- Header: "Republic of the Philippines / Department of Justice / National Bureau of Investigation"
- Official NBI circular logo (eagle with scales) in the upper right.
- Repeating "NATIONAL BUREAU OF INVESTIGATION" security background pattern across the entire page (watermark-style).
- Prominent "MULTI-PURPOSE CLEARANCE" title.
- Red "NO DEROGATORY RECORD" stamp in the remarks section.
- Red "PERSONAL COPY" diagonal marking (common on issued copies).
- Applicant's photo on the right side, naturally integrated.
- QR code (right side) and barcode (usually bottom left) with associated control/reference numbers.
- Signature block with full title: e.g. "JUDGE JAIME B. SANTIAGO (RET.), Director" or "ATTY. DANTE A. GIERRA, CPA, Director" or for older forms "GEN. REYNALDO G. WYCOCO, Director" (director name varies by issuance date; 2003 example uses Gen. Reynaldo G. Wycoco).
- NBI ID number in standard format (e.g. starting with letters then numbers).
- "VALID UNTIL" date clearly shown (e.g. March 2003, valid for one year for travel abroad).
- Fingerprint section (often present as a box or icon) and right thumbprint.
- Consistent security printing, natural paper texture, and proper alignment.
- For 2003-era: Older form layout, "Record Clearance", photo, thumbprint, barcode, clear "No Derogatory Record" statement.

Red flags for forgery: Missing or flat repeating background text, wrong NBI logo design, absent or fake QR/barcode, signature without proper title, photo with digital halo/edge artifacts, inconsistent control number formats, modern elements on old 2003 forms (e.g. current director names on 2003 document).

=== PSA NEGATIVE CERTIFICATION / CENOMAR (CRS Form No. 4) ===
Expected on genuine:
- Header: "Republic of the Philippines / PHILIPPINE STATISTICS AUTHORITY / Manila / OFFICE OF THE CIVIL REGISTRAR GENERAL"
- "CRS Form No. 4 (CENOMAR)" label near the top left with official PSA circular logo.
- Certification text: "We certify that [FULL NAME] who is alleged to have been born on [DATE] in [PLACE] to [FATHER] and [MOTHER], does not appear in our National Indices of Marriages. This certification is based on the records of 1945-[YEAR] marriages enrolled in the database as of [DATE]. Issued upon the request of [REQUESTOR] for [PURPOSE]." (example: APPLE JOY COMENTAN MAALI, November 11, 2004 in Lopez, Quezon to Apolonio Pidoc Maali and Joanna Valeros Comentan, July 25, 2023, BAY LCR for LEGAL PURPOSES).
- QR code and barcode with control/reference numbers (typical format: e.g. 08605-A6-145MAA-00147-ME001).
- Signature of the National Statistician and Civil Registrar General with full title: "CLAIRE DENNIS S. MAPA, Ph. D., National Statistician and Civil Registrar General, Philippine Statistics Authority".
- "Documentary Stamp Tax Paid" marking.
- Standard note: "This certification is not valid if it contains erasures or alterations."
- Light green or security-tinted paper background with visible security pattern when photographed.
- Issued date and purpose clearly stated.
- Clean, professional typography and proper alignment of all elements.

Red flags for forgery: Missing PSA logo or incorrect header wording, absent QR/barcode, wrong signatory title (not Claire Dennis S. Mapa for this period), no "Documentary Stamp Tax Paid", text that deviates from the standard phrasing above, visible digital editing on the form fields, or mismatched control numbers. A normal scan or phone photo of a real CENOMAR with all these features present is genuine - do not classify as digital_scanned.

=== PSA CERTIFICATE OF LIVE BIRTH (Municipal Form No. 102) ===
Expected on genuine:
- Header: "Republic of the Philippines / OFFICE OF THE CIVIL REGISTRAR GENERAL / Philippine Statistics Authority" (often with PSA/NSO logo).
- "Municipal Form No. 102 (Revised January 1993)" or similar form designation.
- Complete structured fields: Child's name (e.g. REINALYN MAGALING), sex, date/place of birth (e.g. 17th NOVEMBER 2004, Tiaong, Quezon), type of birth, birth order, weight at birth (e.g. 3175 grams), parents' full names/maiden name (e.g. Mother: RAQUEL MAGALING, Father: BARTI MAGALING), citizenship, religion (Roman Catholic), occupation (e.g. Housekeeper, Farmer), residence, date/place of marriage of parents (e.g. September 21, 2002 - Tiaong, Quezon).
- Signatures from:
  - Attendant (often "Hilot (Traditional Midwife)" or Physician)
  - Informant (usually the father)
  - Prepared by local civil registrar staff
  - Received by Municipal Civil Registrar (with stamp and signature)
- Bottom section: "Documentary Stamp Tax Paid", control/reference numbers (e.g. 06261-93-145AVC-00379-BI012), barcode, and signature of National Statistician and Civil Registrar General (e.g. "LISA GRACE S. BERSALES, Ph.D." or "CLAIRE DENNIS S. MAPA, Ph. D.").
- "CERTIFIED TRUE COPY" or official stamps from the Civil Registrar's Office.
- Page numbering like "Page 1 of 1, 1 Copy".
- Light security paper or standard civil registry form layout with no erasures/alterations.
- Remarks/annotation section if applicable.
- "BEST POSSIBLE IMAGE" or similar scanning notes may appear.

Red flags for forgery: Incomplete fields, mismatched signatures (e.g., wrong titles or names for the period), missing stamp tax marking, absent or fake barcode/control numbers, text that does not match standard PSA wording, digital artifacts around signatures or stamps, or altered dates/parent details.

Note: Legitimate annotations (e.g., surname change pursuant to R.A. 9255 with date and reference) are normal and expected on some birth certificates.

=== PSA CERTIFICATE OF MARRIAGE (Civil Registry Form) ===
Expected on genuine:
- Official civil registry header: "Republic of the Philippines / OFFICE OF THE CIVIL REGISTRAR GENERAL" with "CERTIFICATE OF MARRIAGE" title.
- Standard fields for: Husband's name, wife's name (maiden), their ages, citizenship, residence, parents' names, date and place of marriage (e.g. "St. Augustine Parish, Bay, Laguna"), marriage license number and date.
- Signatures from:
  - The contracting parties (husband and wife)
  - The solemnizing officer (e.g., parish priest with title)
  - Witnesses (if applicable)
  - Civil registrar officials (prepared by and received by)
- Bottom or side: Marriage license details, date recorded, control/reference numbers, "Documentary Stamp Tax Paid", and often the signature/stamp of the National Statistician and Civil Registrar General (e.g. CLAIRE DENNIS S. MAPA, Ph.D. or LISA GRACE S. BERSALES).
- "Page 1 of 1, 1 Copy" notation.
- Official stamps from the Local Civil Registrar and/or the church/parish.
- Clean layout with no erasures or alterations; handwritten entries in natural style where applicable.

Red flags for forgery: Missing license number or date, incorrect solemnizing officer title (e.g. wrong priest name or title), mismatched parent details, absent PSA stamp or control numbers, signatures that look traced or digitally inserted, layout that doesn't match standard civil registry marriage form.

=== LTO CERTIFICATE OF REGISTRATION (OR/CR) – Motor Vehicle (e.g. Motorcycle with Sidecar / Tricycle) ===
Expected on genuine:
- Official LTO form with blue border, correct header "CERTIFICATE OF REGISTRATION" and LTO logos.
- Vehicle details: Plate No. (e.g. D624MI), Engine No., Chassis No., Make/Model (e.g. Kawasaki), Type of Body (e.g. with Sidecar), Color, Year Model, etc.
- Owner’s complete name, address, and citizenship.
- CR Number (Certificate of Registration Number) and other reference numbers.
- Barcode.
- Signature of authorized LTO official with full title (e.g. "ATTY. VIGOR D. MENDOZA II, Assistant Secretary" or similar current official).
- Official LTO dry seal or stamp if applicable.
- Clean printed layout, no alterations to key fields.

Red flags for forgery: Mismatched plate/engine/chassis numbers, wrong or absent official signature/title, missing barcode or CR number, altered vehicle details, poor quality printing or border, or digital artifacts on the form.

=== PHILIPPINE BANKNOTE (e.g. ₱20, ₱50, ₱100, ₱200, ₱500, ₱1000) ===
Expected on genuine:
- For ₱20 front: Portrait of Manuel L. Quezon, serial format (e.g. CS28040), signatures of President Ferdinand R. Marcos Jr. and BSP Governor Eli M. Remolona Jr., "DALAWAMPUNG PISO".
- For ₱20 back: Banaue Rice Terraces scene with "DALAWAMPUNG PISO".
- For ₱100 front: Portrait of Manuel A. Roxas with correct details, signatures of President Ferdinand R. Marcos Jr. and BSP Governor Eli M. Remolona Jr., serial number format (e.g. HS646207, XH169666), security features like watermark area, security thread, color-shifting elements, microprinting, and proper coat of arms.
- For ₱100 back: Mayon Volcano landscape with whale shark, map of the Philippines, denomination details, and the standard security background patterns and color scheme for the New Generation Currency reverse.
- For ₱50 front: Portrait of Sergio Osmeña, Leyte Landing historical scene, Visayan Leopard Cat vignette, serial number format (e.g. AH4929962), and the correct “LIMAMPUNG PISO” layout with detailed wildlife engraving.
- For ₱50 back: Correct design showing Taal Lake with fish (Maliputo / Caranx ignobilis), map outline, proper denomination, and the expected security background patterns and color scheme.
- For ₱500: New Generation Currency design with portrait of Visayan Spotted Deer (Rusa alfredi), serial number format (e.g. AL6879411 or AM8127695), signatures of President Ferdinand R. Marcos Jr. and BSP Governor Eli M. Remolona Jr., back side shows Puerto Princesa Subterranean River National Park (UNESCO) with map and Blue-naped Parrot, visible security features (color-shifting ink, watermark area, security thread, microprinting).
- For ₱1000: New Generation Currency design with correct portrait (e.g. the featured hero on front, such as Jose Abad Santos and Vicente Lim), serial number format (e.g. BN5838335, BN5538335, BV6727980, HZ611893), signatures of President Ferdinand R. Marcos Jr. and BSP Governor Eli M. Remolona Jr., back side shows Tubbataha Reefs Natural Park (UNESCO) with map and marine elements (or birds and historical figures), visible security features (color-shifting ink, watermark area, security thread, microprinting, holographic patches with iridescent shifting).
- For ₱200: Portrait of Diosdado Macapagal, back with Chocolate Hills or relevant landmark.
- For older NDS notes: the vintage design, watermark portrait, embedded thread, serial formatting, and reverse layout must match the valid legacy note for that denomination; older styling alone is not a counterfeiting indicator.
- Holographic security patch (close-up): Iridescent color-shifting effect (rainbow/blue/gold shifting when tilted), detailed engraved patterns (e.g. intricate designs around a central emblem with "1000"), embedded in the note with fine line work and micro elements that align perfectly with the surrounding print.
- Under UV light (UV Light Check for ₱200 and ₱20): Proper fluorescent security features visible under UV light (security threads, fluorescent inks, and patterns). Correct UV reaction patterns for ₱200 and ₱20 notes. Bright threads and security inks reacting correctly with uniform, denomination-specific glow. No irregular glowing, missing security elements, dull response, or anomalous fluorescence that are common in counterfeits. The UV response is consistent with authentic BSP-issued Philippine currency notes.
- Overall: Official BSP design, paper texture, high printing quality, precise alignment, color accuracy. When tilted or held to light, security features (hologram, thread, watermark) must respond correctly. Microprinting and fine lines are sharp and legible under magnification.
- No modern digital elements; paper should feel crisp with proper security threads embedded.

**IMPORTANT NOTE ON SECURITY FEATURES (applies to both genuine and forged specimens)**: Many forged/counterfeit banknotes ("all of them" in specimen sets) deliberately include visible simulated security features — a printed line or dashed element mimicking a security thread, a printed or sticker-like area for hologram/watermark, color-shifted ink simulation, microtext printed at normal resolution, serial numbers, portraits, and background patterns. Presence of "security features" alone does NOT mean genuine. 

Red flags for forgery: Poor printing quality, mismatched colors, fake or absent security features (e.g. no shifting color on denomination or hologram looks flat/static without rainbow shift, wrong thread position or missing), incorrect serial number format, wrong signatures (e.g. not current President/Governor), digital artifacts (e.g. pixelation around hologram or microprint looks blurry or copied), or paper that feels wrong. Holographic patches on genuine notes have complex, multi-layer iridescence and fine engraving that fakes often lack. Under UV, counterfeits often show weak, absent, or unnatural glowing instead of bright, denomination-specific fluorescence. A clear UV photo of genuine ₱200 and ₱20 notes displaying the expected bright fluorescent threads, inks, and correct patterns = no_forgery_detected.

**Specific indicators that security features are simulated/forged (even when visibly "present")**:
- Security thread appears as a flat printed line, solid bar, or surface ink (often dashed or with visible halftone dots) instead of a true embedded, windowed, or metallic/plastic strip with proper depth and transmission when held to light.
- Hologram or iridescent patch is a flat printed graphic or adhesive sticker; it shows no (or very weak) angle-dependent rainbow/blue/gold multi-layer shift, lacks fine engraved micro-details, or has edge artifacts/pixelation.
- Watermark area is just printed shading or grayscale ink instead of a true translucent multi-tone embedded design that becomes clearly visible and sharp only when backlit/transmitted light is used.
- Microprinting (fine text around portraits, denomination, or borders) is visible at normal viewing distance or has the same sharpness/resolution as the main text instead of being significantly finer and crisp only under magnification; often blurry or broken in fakes.
- Color-shifting elements (denomination numbers or patches) show little or no real shift, shift to the wrong colors, or look like simple printed gradients.
- Fluorescent elements under UV (if present) glow incorrectly (wrong color, too uniform, in wrong positions, or the "thread" glows but the surrounding paper/inks react unnaturally).
- Overall: ink density, paper texture, and alignment of "features" are inconsistent with genuine BSP production (e.g. features sit on top of the paper surface rather than integrated).
- Even high-quality forgeries that copy portraits, serials (correct format), backs (correct scenes), and add fake threads/holograms will fail one or more of the above physical/optical tests.

Classify as currency_analysis (forgery) when security features are present but fail the above quality, behavior, embedding, or reaction tests — especially when multiple "features" are simulated at once. A note that looks complete with all typical security elements but they are all low-fidelity simulations = forged.

=== PHILIPPINE POSTAL IDENTITY CARD (PhlPost ID) – Premium ===
Expected on genuine:
- Official header: "REPUBLIC OF THE PHILIPPINES Philippine Postal Corporation POSTAL IDENTITY CARD" with PhlPost logo.
- Holder's photo on the left.
- Name in large font (e.g. LORENA BUQUIR MANALO).
- Address, Date of Birth (e.g. 22 Apr 84), Nationality (PHL), Issuing Post Office (e.g. QUEZON), Valid Until date (e.g. 27 Nov 22).
- PRN number (e.g. G40190591480 P).
- Handwritten signature of the holder.
- "POSTAL ID" logo and small ID icon.
- Large QR code on the right.
- "PREMIUM" marking in bold.
- Back side: PHLPOST logo, website (www.phlpost.gov.ph), disclaimer text about being proof of identity, barcode (e.g. 22872947), signature of Postmaster General & CEO (e.g. Joel L. Otarra).
- Security features: background patterns, perhaps subtle holographics or watermarks.

Red flags for forgery: Wrong or missing Postmaster General signature for the period, mismatched PRN format, absent QR or barcode, "PREMIUM" marking missing or wrong, digital artifacts on photo/signature, incorrect issuing office, or layout that doesn't match standard PhlPost design.

=== DepEd SCHOOL IDENTIFICATION CARD (School ID) ===
Expected on genuine:
- Official school and DepEd branding with school logo (e.g. CALAMBA CITY SCIENCE INTEGRATED SCHOOL 2010 with atom/gear/plant design).
- Holder's photo on the right or bottom.
- Name in large font (e.g. GASTADOR Deen Alpearl G.).
- LRN in format (e.g. 109814100102).
- Grade/Section or details (e.g. 12 ISAROG S.Y 2022 - 2023).
- School ID number (e.g. 308704).
- DepEd logo prominently displayed.
- Clean printing on plastic card with school colors (e.g. purple background).
- Vertical "SENIOR HIGH SCHOOL" text if applicable.
- No digital artifacts, consistent with printed school-issued ID.

Red flags for forgery: Mismatched school logo design, incorrect LRN format, absent or fake DepEd logo, digital photo artifacts, wrong school year or ID number, or layout that doesn't match standard DepEd school ID template.

=== PHILIPPINE NATIONAL ID (PhilID / ePhilID) ===
Expected on genuine:
- Official header: "REPUBLIKA NG PILIPINAS / Republic of the Philippines PAMBANSANG PAGKAKAKILANLAN / Philippine Identification Card" with PSA branding.
- PhilID Number in format XXXX-XXXX-XXXX-XXXX (e.g. 3469-2753-1568-0574 or 4971-5326-1465-1035).
- Holder's photo on the left.
- Last Name, Given Names, Middle Name (e.g. CALINGA KARELL AVERION or RECTO GIAN-DREY TOLEDO).
- Date of Birth (e.g. AUGUST 11, 2004 or SEPTEMBER 29, 2004).
- Address (e.g. 452 PUROK 6, SANTIAGO 1, CITY OF SAN PABLO, LAGUNA or 773 PUROK 6, SAN LUCAS 2, CITY OF SAN PABLO, LAGUNA).
- Nationality "PHL".
- QR code with red/blue border.
- Colorful security background with wavy patterns, stars, and holographic elements.
- Small secondary/ghost image or security features.
- Clean printing, no digital artifacts.

Red flags for forgery: Incorrect PhilID number format, mismatched photo vs details, absent or fake QR, wrong header/logo, digital halo on photo or text, incorrect address format, or background that doesn't match the official colorful design.

=== PHILHEALTH ID CARD ===
Expected on genuine:
- Official green card design with "REPUBLIC OF THE PHILIPPINES Philippine Health Insurance Corporation" and PhilHealth logo ("Your Partner in Health").
- PhilHealth Number in format XX-XXXXXXXXX-X (e.g. 11-251897314-5).
- Holder's photo on the left.
- Name (e.g. AMANTE, JOHN EMMANUELLE BUISON).
- Date of Birth and Sex (e.g. AUGUST 19, 2004 - MALE).
- Address (e.g. BLOCK 1 SAMPAGUITA ROAD SILANGAN SUBD, DAYAP, CALAUAN, LAGUNA).
- QR code on the right.
- Handwritten signature.
- Security features: green map background of Philippines, subtle patterns.
- Clean printing, no digital artifacts.

Red flags for forgery: Wrong number format, mismatched photo/details, absent or fake QR, incorrect branding/logo, digital halo on photo or text, or background that doesn't match the standard green PhilHealth design.

=== DRIVER’S LICENSE (LTO) ===
Expected on genuine:
- Official LTO design with header, logos, and security background.
- Visible holographic security features (tilt to see shifting effects).
- Proper fields: License No. (e.g. D14-22-001444), Agency Code (e.g. D14), expiration date.
- Personal details, photo, signature.
- Signature of authorized official (e.g. Edgar C. Galvante, Assistant Secretary).
- Barcode or other security elements.

Red flags for forgery: Missing or static hologram, incorrect license number format, wrong agency code, absent or fake signature/title, digital artifacts on photo/hologram, or layout that doesn't match standard LTO design.

=== PHILIPPINE e-PASSPORT ===
Expected on genuine:
- Official header "REPUBLIC OF THE PHILIPPINES" with Department of Foreign Affairs (DFA) branding.
- "PHILIPPINE PASSPORT" or e-Passport designation.
- Holder's photo on the left, with secondary facial image on the right (standard in current e-passports).
- Personal details: surname, given names, nationality (PHL), date of birth, sex, place of birth, date of issue, date of expiry, issuing authority (e.g. DFA San Pablo or DFA Lucena).
- Visible holographic “PHL” element with rainbow shifting effect (tilt to verify).
- Machine Readable Zone (MRZ) at the bottom with properly formatted lines (two lines of 44 characters each).
- Passport number (e.g. P0673965D).
- Signature of the holder.
- Security features: holograms, microtext, UV elements, watermarks, etc. (visible in proper lighting/tilt).
- Back cover or data page with additional security.
- Validity example: until August 13, 2033.

Red flags for forgery: Missing or static (non-shifting) hologram, incorrect MRZ format or check digits, absent secondary photo, wrong issuing office or dates, digital artifacts on photo or hologram area, mismatched passport number style, or poor quality printing.

=== PROVINCIAL GOVERNMENT EVENT PARTICIPATION CERTIFICATE (e.g. Amiling Festival / Anilag Cosplay Competition 2025) ===
Expected on genuine:
- Header with "PROVINCIAL GOVERNMENT OF LAGUNA" and "REPUBLIC OF THE PHILIPPINES", colorful "Amiling Festival 2025" sunburst logo, "CERTIFICATE OF PARTICIPATION".
- "I ❤️ LAGUNA" and "LOVE THE PHILIPPINES" branding elements.
- Presented to [name] (e.g. Anie Joy S. Banag).
- "In recognition of his/her showcased talent in the ANILAG COSPLAY COMPETITION 2025 with the theme 'Sama Sama Tayo sa Lugar na Saya sa Laguna'".
- "Given this 14th day of March, 2025 at the Time Plaza, Provincial Capitol Compound, Santa Cruz, Laguna."
- Signatures:
  - Ms. Pamela Jane P. Baun, Events and Program Chairman (signature on left).
  - Ramill V. Hernandez, Governor, Province of Laguna (signature on right).
- Modern colorful design with fireworks, stars, and diagonal red/blue accents.
- Official Laguna provincial logos and seals.

Red flags for forgery: Wrong governor name (not Ramill V. Hernandez for 2025 events), incorrect venue/date, mismatched logo colors/designs, digital halo or artifacts on signatures/logos, absence of provincial branding, or inconsistent formatting.

=== GENERAL RULES FOR GENUINE CERTIFICATES, CLEARANCES, AND GOVERNMENT FORMS ===
- Official logos and headers must be crisp, correctly colored, and match the issuing agency's current design. For documents from the early 1990s, expect old "KAGAWARAN NG EDUKASYON KULTURA AT ISPORTS" (DECS) branding instead of modern DepEd.
- Security features (repeating background patterns, embossed/holographic seals, watermarks) must show **physical interaction** with the paper (shadows, raised texture, ink/seal effects, or visible reflectance in photos).
- Signatures should display natural pen pressure variation and proper title blocks (e.g. "Director", "National Statistician and Civil Registrar General", "Schools Division Superintendent").
- Serial numbers, control numbers, reference numbers, LRNs (post ~2000s), and QR/barcodes must be present and follow the agency's standard format for the era.
- Stamps such as "NO DEROGATORY RECORD", "Documentary Stamp Tax Paid", or "PERSONAL COPY" must appear in the correct color, position, and style.
- When multiple security features are expected (QR + barcode + official seal + background pattern + proper signature), the genuine document will have **most or all** of them executed correctly and consistently.
- Old DECS elementary diplomas (Katibayan) from the early 1990s use gold embossed school seals, period-specific printing/typography, natural paper aging (yellowing, creases), and superintendent names appropriate to that time (e.g. Joseph A. Roque in 1993). No QR codes, LRNs, or modern DepEd branding.
- PSA documents (CENOMAR, birth/marriage certificates) commonly use light green security paper and include a clear "not valid if altered" note. Legitimate annotations (e.g. surname change per RA 9255 with date) are normal.
- NBI clearances commonly feature a repeating "NATIONAL BUREAU OF INVESTIGATION" background + red stamps + photo + QR/barcode.
- LTO OR/CR forms use blue borders, official LTO logos, vehicle specs (plate, engine, chassis), owner details, and authorized Assistant Secretary signature.
- Provincial event participation certificates (e.g. Amiling Festival) use colorful Laguna government branding, specific governor signatures (e.g. Ramill V. Hernandez), event chairman signatures (e.g. Pamela Jane P. Baun), and modern design elements.
- Old Original Certificates of Title (Free Patent, Judicial Form 54-D from 1985) use old judicial form headers (National Land Titles and Deeds Registration Administration), presidential signature (Ferdinand E. Marcos), Director of Lands signature (Benjamin F. Dumalo), old legal language, and significant paper aging.
- Older NBI forms (e.g. 2003) use Gen. Reynaldo G. Wycoco as Director, photo, thumbprint, barcode, "No Derogatory Record", and period-specific layout valid for travel.
- Philippine Postal IDs (PhlPost Premium) feature official PhlPost branding, photo, signature, QR code, barcode, "PREMIUM" marking, PRN, and Postmaster General signature (e.g. Joel L. Otarra).
- Philippine e-Passports include holographic “PHL” with shifting effect, MRZ, secondary facial image, DFA issuing office (e.g. DFA San Pablo or DFA Lucena), validity dates (e.g. until August 13, 2033), and proper passport number format.
- Philippine National IDs (PhilID / ePhilID) feature PSA branding, colorful security background, QR code, 16-digit PhilID number (e.g. 4971-5326-1465-1035 or 3469-2753-1568-0574), photo, personal details (e.g. Last Name CALINGA, Given Names KARELL AVERION), and holographic elements.
- Driver’s Licenses (LTO) feature official LTO design, holographic features, License No. (e.g. D14-22-001444), Agency Code, and signature of Assistant Secretary (e.g. Edgar C. Galvante).
- DepEd School IDs feature official school logo (e.g. Calamba City Science Integrated School 2010), DepEd logo, LRN (e.g. 109814100102), student name, grade/section (e.g. 12 ISAROG), school year (e.g. S.Y 2022 - 2023), School ID number (e.g. 308704), and photo on plastic card with school colors.
- PhilHealth ID Cards feature green design with PhilHealth logo, PhilHealth Number (e.g. 11-251897314-5), photo, QR code, signature, address, and map background.
- Philippine Banknotes (e.g. ₱20, ₱50, ₱100, ₱200, ₱500, ₱1000) feature correct portraits (e.g. Manuel L. Quezon for ₱20, Sergio Osmeña for ₱50, Manuel A. Roxas for ₱100, Diosdado Macapagal for ₱200, Visayan Spotted Deer for ₱500, appropriate hero for ₱1000), current signatures (e.g. President Ferdinand R. Marcos Jr. and BSP Governor Eli M. Remolona Jr.), serial formats (e.g. CS28040 for ₱20, AP562952 for ₱50, MV67490 for ₱100, AL6879411 for ₱500, BN5838335, BN5538335, BV6727980, HZ611893 for ₱1000), security elements (watermark, thread, color-shift, microprint, holographics), backs: Banaue Rice Terraces for ₱20, Taal Lake/Tilapia for ₱50, Mayon for ₱100, Chocolate Hills for ₱200, Puerto Princesa Subterranean River (UNESCO) with Blue-naped Parrot for ₱500, Tubbataha Reefs for ₱1000 (or birds and historical figures). Close-up holographic patches show iridescent multi-color shifting (blue/gold/rainbow) with detailed engraving and fine lines that align perfectly. Under UV light (including dedicated UV Light Checks): genuine notes (esp. ₱200 and ₱20) show proper fluorescent security features (security threads, fluorescent inks, and patterns) with correct UV reaction patterns, bright threads and security inks reacting correctly, uniform denomination-specific glow, and no irregular/dull/missing elements. Counterfeits often have weak, absent, or unnatural glowing. 

**Key distinction for forged specimens**: Even forged notes in specimen sets frequently display visible "security features" (printed thread lines, simulated hologram patches, shaded watermark zones, microtext, color attempts, correct-looking serials/portraits/backs). These are simulations. Genuine notes have embedded, optically responsive, high-fidelity security elements that behave correctly under tilt, backlight, and UV. A note with all features "present" but executed as flat prints, stickers, or low-quality simulations = currency_analysis forgery.
- **PHOTO/SCAN NOTE**: Genuine documents are frequently submitted as phone photos or scans. When the underlying document features match the expected authentic pattern (seals, stamps, background, signatures, layout), classify as no_forgery_detected regardless of typical photo/scan artifacts. Old documents will show natural aging.

DECISION RULE:
  1. Identify the document type from layout, logos, and text (CTC, LTFRB, DepEd/DECS diplomas including old Katibayan, NBI Clearance including 2003 forms, PSA CENOMAR, university diploma, Certificate of Live Birth, LTO OR/CR, Certificate of Marriage, Provincial Event Participation Certificates like Amiling Festival, Old Original Certificate of Title / Free Patent 1980s, Philippine Postal ID (PhlPost), Philippine National ID (PhilID / ePhilID), Driver’s License (LTO), DepEd School IDs, PhilHealth ID, e-Passport, Philippine Banknotes ₱20/₱50/₱100/₱200/₱500/₱1000 including UV light checks / close-up holographics and fluorescent security features (e.g. serials BV6727980 and HZ611893 for ₱1000, proper UV threads/inks/patterns for ₱200 and ₱20); forged notes frequently simulate all security features (printed threads, flat holograms, etc.) — evaluate execution quality and behavior, etc.).
  2. Check whether the expected genuine security features and formatting for that exact type are present and correctly executed (see sections above). Treat phone photos and scans of real documents as normal. Old documents (1985 land titles, 2003 NBI, 1990s diplomas) will have period-specific branding, paper aging, and no modern features like QR codes.
  3. Only move to a forgery category if there is clear, specific evidence of tampering, insertion, tracing, or digital compositing that overrides the positive authentic indicators.
  4. When positive genuine indicators are strong and consistent across the document, lean **heavily** toward "no_forgery_detected" even if minor wear, creases, or photo/scan artifacts exist.

Use this section as the PRIMARY filter for certificates, diplomas, clearances, and government forms before applying the forgery category rules below.
═══════════════════════════════════════════════════════════════════════════

REASONING - work through these steps in order before you classify:
  1. What is in the image? (document or non-document; if document, what type? Use the GENUINE DOCUMENT VERIFICATION section above first.)
  2. Run the AUTHENTICITY FIRST CHECK - EVEN IF IT LOOKS SCANNED OR PHOTOGRAPHED:
     Check if this shows the expected positive genuine features for its type (CTC red seal + treasurer stamp e.g. Jenalyn Cabrera Sergio as Brgy Treasurer, NBI repeating background + "NO DEROGATORY RECORD" + photo + Director signature like DANTE A. GIERRA or Gen. Reynaldo G. Wycoco in 2003, PSA header + stamps + Mapa signature + control numbers, old 1990s DECS elementary Katibayan with gold embossed seal, period DECS header, paper aging, and 1993 superintendent signature like Joseph A. Roque, diplomas with embossed seals + LRN + correct titles, birth cert with proper fields and registrar signatures, 1985 Original Certificate of Title with Ferdinand E. Marcos presidential signature and Benjamin F. Dumalo Director of Lands, old judicial form language and significant paper aging, PhlPost ID with photo, QR, barcode, "PREMIUM", Postmaster General signature (e.g. Joel L. Otarra), PhilID / ePhilID with PSA branding, QR, PhilID number (e.g. 4971-5326-1465-1035 or 3469-2753-1568-0574), colorful background, photo and address (e.g. CALINGA KARELL AVERION, AUGUST 11, 2004, 452 PUROK 6, SANTIAGO 1, CITY OF SAN PABLO, LAGUNA), Driver’s License with LTO branding, holographics, License No. (e.g. D14-22-001444), signature of Edgar C. Galvante, DepEd School ID with school logo (e.g. Calamba City Science Integrated School), DepEd logo, LRN (e.g. 109814100102), name (e.g. GASTADOR Deen Alpearl G.), S.Y (e.g. 2022-2023), School ID (e.g. 308704), photo, PhilHealth ID with green design, PhilHealth logo, number (e.g. 11-251897314-5), photo, QR, signature, e-Passport with holographic PHL shifting, MRZ, secondary photo, DFA office (e.g. DFA Lucena), validity until August 13, 2033, Philippine Banknotes with correct portraits (Roxas for ₱100, Visayan Spotted Deer for ₱500, appropriate for ₱1000), signatures (Marcos Jr. + Remolona), serials (e.g. AL6879411 for ₱500, BN5838335 for ₱1000), security (watermark, thread, color-shift, microprint) for ₱500/₱1000, and Puerto Princesa Subterranean River; plus UV Light Check examples for ₱200 and ₱20 showing proper fluorescent security threads, fluorescent inks and patterns, correct UV reaction patterns, bright threads/security inks reacting correctly with no irregular/missing/dull glow (consistent with authentic BSP notes). Forged notes (e.g. specimen sets) often include visible but simulated versions of threads, holograms, watermarks, microprint etc. — these must be evaluated for fidelity, embedding, optical response, and UV correctness; presence alone does not indicate genuine. / Tubbataha Reefs on backs; close-up holographics show iridescent shifting rainbow/blue/gold with detailed engraving and fine lines, etc.).
     A normal phone photo or scan of a genuine document with these features = no_forgery_detected. Do not let typical scan/photo appearance override authentic features. Old documents will show natural aging and era-specific branding.
  3. Only if the positive genuine indicators are weak, missing, or contradicted, then scan for anomalies. List EVERY anomaly.
  4. For each anomaly, ask: is this real tampering, or one of the IGNORE items above (including normal photo/scan artifacts)? Cross-check against the genuine patterns in the section above.
  5. CRITICAL BRANCHING QUESTION: Can I see PHYSICAL PEN MARKS or HAND-DRAWN INK EVIDENCE (grooves, tremor, hesitation, carbon residue)? OR is this PERFECT DIGITAL TYPOGRAPHY (uniform font, zero pen variation)?
     - YES (pen marks visible) → consider traced_carbon, traced_indentation, traced_projection
     - NO (perfect digital typography) → consider digital_desktop, digital_cut_paste, digital_scanned
  6. If there are MULTIPLE anomalies within your chosen branch, decide which is the PRIMARY forgery (the one that changes the document's legal meaning).
  7. Point to the PRIMARY anomaly's LOCATION (which region of the document).
  8. Pick the single best category code based on the PRIMARY evidence.
  9. Set confidence based on how clear the evidence is (see scale below). If strong positive genuine features are present and consistent, heavily favor "no_forgery_detected".
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
  1. The "explanation" MUST begin with the category's human name (e.g. "Chemical Erasure detected." or "No Forgery Detected.").
  2. For no_forgery_detected: First confirm strong positive genuine indicators from the GENUINE DOCUMENT VERIFICATION section (correct logos, embossed/holographic seals, serial/LRN/Special Orders, proper signatory titles, verification features, natural physical interaction). Minor wear or photo artifacts do not invalidate genuine documents.
  3. If you classify as no_forgery_detected, set anomaly_location to null and evidence to [] or just observed-clean items (e.g. "correct red municipal seal present", "gold embossed school seal with ribbon", "holographic LTFRB sticker visible").
  4. Do NOT invent evidence. If you can't see it, don't list it.
  5. Pick exactly ONE category. If torn, pick the dominant one and mention the other in the alternatives array.
  6. Output ONLY the JSON object. No code fences, no commentary.
  7. "alternatives" must be a JSON array (never null - use [] if there are none). Include up to 3 alternatives ordered by likelihood. Populate it whenever: confidence is below 0.90, OR multiple categories fit the evidence almost equally, OR image quality limits certainty. Leave it as [] only when the evidence is completely unambiguous. Be honest - it is better to admit ambiguity than to over-commit."""


# ═══════════════════════════════════════════════════════════════════════════
# AUXILIARY PROMPTS
# Used by the optimization pipeline functions defined below in this file.
# ═══════════════════════════════════════════════════════════════════════════

# ───────────────────────────────────────────────────────────────────────────
# TRIAGE_PROMPT - Stage 1 quick classification (~700 tokens, $0.00005)
# Used by triage_classify() to seed alternatives in the main result.
# ───────────────────────────────────────────────────────────────────────────

TRIAGE_PROMPT = """You are a forensic document examiner doing a quick triage classification.

Look at this document and pick the TOP 3 most likely forgery categories. Strongly consider "no_forgery_detected" if it shows strong positive genuine features (correct logos, seals, stamps, background patterns, signatures, reference numbers, QR codes) even if the image is a phone photo or scan. See GENUINE DOCUMENT VERIFICATION knowledge for CTCs, LTFRB certificates, DepEd/DECS diplomas (including old 1990s Katibayan), university diplomas, NBI Clearances (including 2003 with Wycoco), PSA CENOMARs, Certificate of Live Birth, LTO OR/CR, Provincial Event Participation Certificates like Amiling Festival, Old Original Certificate of Title / Free Patent 1985 with Marcos signature, Certificate of Marriage, PhlPost IDs, PhilID / ePhilID, Driver’s Licenses (LTO), DepEd School IDs, PhilHealth IDs, e-Passports, and Philippine Banknotes (₱20/₱50/₱100/₱200/₱500/₱1000 including close-up holographics with shifting colors and engraving, plus UV light checks showing bright fluorescent security threads/inks/patterns for ₱200 and ₱20 with correct reaction patterns).

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
  obliteration_pigment    - Opaque marker/paint
  sympathetic_indented    - Indented writing under raking light
  sympathetic_special     - Hidden ink (invisible, UV, heat-activated)
  currency_analysis       - Counterfeit currency
  no_forgery_detected     - Authentic document (strongly prefer when expected genuine features like correct logos, embossed/holographic seals, repeating background patterns, proper stamps/signatories, verification QR are present and well executed - even on a photo or scan)
  not_a_document          - Not a document
  other                   - Other forgery

Return ONLY valid JSON:
{
  "top_3": ["category_code", "category_code", "category_code"],
  "reasoning": "brief reason why these three. If strong genuine features are present for a known document type (CTC, LTFRB, NBI including 2003, PSA birth cert/CENOMAR, diplomas including old 1990s, LTO, Amiling Festival certificates, 1985 land titles with Marcos, Certificate of Marriage, PhlPost ID, PhilID / ePhilID (e.g. 3469-2753-1568-0574 CALINGA KARELL AVERION), Driver’s License (LTO), DepEd School IDs, PhilHealth IDs, e-Passport (e.g. DFA Lucena until 2033), Philippine Banknotes with Roxas portrait/current signatures/serial/security for ₱100 and Taal Lake/“LIMAMPUNG PISO” for ₱50 back; close-up holographics with iridescent shifting and engraving for ₱1000/₱500; UV light checks for ₱200 and ₱20 with proper fluorescent security features (threads, inks, patterns), correct UV reaction patterns, bright consistent glow and no irregular/missing elements (genuine BSP response); forged specimens often show simulated versions of all these features (printed thread, flat hologram sticker, printed watermark shading, etc.) that fail physical/optical tests — do not mistake presence of fake features for genuine, etc.), include no_forgery_detected in top 3."
}
"""


# ───────────────────────────────────────────────────────────────────────────
# CATEGORY_DETAIL - Per-category detail dictionary
# Used by build_detailed_prompt() to construct a focused prompt that only
# describes the top-3 categories from triage (saves text tokens).
# ───────────────────────────────────────────────────────────────────────────

CATEGORY_DETAIL = {
    "traced_carbon": """
    traced_carbon - Carbon-paper transfer: forger places carbon under a genuine signature or model writing and traces, transferring carbon which is then inked over.
    Look for: powdery gray/black carbon deposits, faint smudges, circular or oval transfer marks in and around the strokes, and stray particles outside the main writing.
    Pay special attention to pressure points, loops, and complex flourishes where carbon residue collects, repeated specimen attempts with similar letter formations, retracing marks, mechanical stroke uniformity, hesitation/tremor, uniform line weight, and lack of natural speed or pressure variation.
    Also look for slight misalignment between the inked line and the underlying transfer.
    """,

    "traced_indentation": """
    traced_indentation - Pressure indentation / canal light: look for indented impressions, depressed outlines, or a groove around letter shapes where the pen pressed into paper.
    Look for: powder-enhanced or oblique-light impressions, consistent depth, repeated pressure marks or multiple trace attempts, matching letter formation to an overlying document, and lack of visible ink in the indented area.
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
    Look for: dense, multi-stroke black ink or dark ink applied in overlapping horizontal and diagonal strokes, uniform fresh coverage, irregular edge patterns, stray extension lines, and multiple passes designed to maximize concealment of underlying writing.
    Also look for dense vertical stroke blocks and cross hatch patterns, where repeated up/down and back-and-forth motions indicate thorough masking after tracing underlying content.
    Compare visible overlays with known reference text such as "BALLET" to detect matching shapes, stroke lengths, and contour alignment.
    Note when different ink variants are used in the same set: dark black ink may represent same-ink obliteration, while brownish/reddish ink indicates a different pen or ink type used to reinforce concealment or introduce texture variation.
    Under alternate light (blue/UV/orange), the obliterated area may show high contrast with the paper, revealing layered applications, foreign ink composition, and repeated tracing/overwriting designed to hide a name or signature.
    Consider traced obliterated writing when the obliteration appears methodical, follows the shape of hidden letters or signature elements, and is inconsistent with legitimate redaction markings.
    """,

    "obliteration_whiteout": """
    obliteration_whiteout - Correction fluid covering text.
    """,

    "obliteration_pigment": """
    obliteration_pigment - Opaque marker, paint, or pigment covering text.
    """,

    "sympathetic_indented": """
    sympathetic_indented - Sympathetic indented writing: hidden pressure impressions visible only by raking/oblique light, powder enhancement, ESDA-style visualization, or surface shadowing, with no visible ink.
    Look for subtle letter or word outlines (e.g. ANGER, HAPPY, EMPTY), consistent depth and pressure-gradient edges, raised or depressed surface contours, and faint overlapping trace marks from repeated pressure strokes. Focus on paper fiber disturbance, surface texture changes, and shadowing in the impressed areas rather than any ink or pigment. This category is for secondary impressions transferred from an overlying document or top sheet; the complete absence of ink in the impression area is the strongest distinguishing feature from genuine writing or traced ink.
    """,

    "sympathetic_special": """
    sympathetic_special - Invisible/special ink revealed by external stimulus (heat, UV, chemical reagent).
    Look for faint brownish/yellowish stains, uneven absorption, irregular diffusion patterns, greasy sheen, or waxy residue in paper fibers rather than clear pen line structure.
    Pay special attention to organic latent inks such as lemon/calamansi, vinegar, sugar water, milk, oil, wax, and dilute water solutions that become visible with heat, chemical development, or oblique lighting.
    Key indicators:
      - irregular edge diffusion and blotchy staining
      - uneven paper fiber darkening with no crisp ink outline
      - text that only appears after heat or reagent application
      - absorption-induced feathering rather than a sharp pen stroke
      - spidery or mottled organic flow patterns typical of fruit juices or natural acids
      - acidic brownish stains and oxidation patterns consistent with vinegar
      - protein residue, bubbling, or slight scorching consistent with milk-based latent ink
      - translucent greasy sheen, haloing, or oily diffusion consistent with oil-based latent ink
      - waxy or crystalline residue, slight raised texture, or caramelization consistent with wax/sugar-based ink
      - ultrafaint marks that may require oblique light or enhancement, consistent with water/dilute latent ink
    If the substance is not certain, propose the most likely candidate and specify in the explanation (e.g. "likely vinegar", "likely milk", "likely oil", "likely wax", or "likely phenolphthalein").
    """,

    "currency_analysis": """
    currency_analysis - Suspected counterfeit banknote.
    Key evaluation: Even if the note displays visible security elements (printed thread, hologram area, watermark shading, serials, portraits, microtext, color attempts), verify that those features are authentic and physically integrated.
    - Genuine Philippine banknotes should show high-quality physical security features appropriate for the note’s issuance series and denomination:
      * New Generation Currency (2020, 2021, 2024, 2025 BSP series) notes should show a true optically variable feature or holographic patch that shifts color and reveals fine engraved detail when tilted;
      * an embedded security thread or clear window with printed coat-of-arms/denomination elements that interact with paper fiber and light;
      * genuine intaglio printing or embossed texture in the portrait/vignette area with crisp, high-relief lines;
      * a translucent watermark or shadow image visible with transmitted light, matching the portrait or denomination;
      * ultra-fine sharp microtext, accurate serial formatting, and correct year/letter prefixes for the series.
      * Older New Design Series (NDS) notes should show the older era-specific portraits, watermark portrait, embedded thread, see-through feature, security fibers, and color palette/layout that match the valid legacy design for that denomination.
    - BSP New Generation Currency (NGC) series-specific features:
      * ₱50: Sergio Osmeña front with Leyte Landing scene, correct serial layout, tactile dots, shadow thread, vertical clear window, microprinting, UV-reactive map outlines, and reverse Taal Lake with fish vignette, map of the Philippines, and accurate denomination labeling.
      * ₱100: Manuel A. Roxas front with proper portrait details, current signature placement, serial formatting (e.g. HS646207, XH169666), enhanced value panel, shadow thread, microprinting, tactile dots, and reverse Mayon Volcano with whale shark, map features, and standard NGC security printing.
      * ₱200: optical variable ink panel, clear window, shadow thread, watermark, microprinting, correct portrait rendering, UV-reactive island map and fibers.
      * ₱500: shadow thread, dynamic wave, tactile dots, vertical clear window, flying eagle watermark, crisp deer vignette, expected UV security marks.
      * ₱1000: Sampaguita clear window, shadow thread, tactile dots, microprinting, dynamic wave, flying eagle watermark, color-shifting denomination numerals, correct UV-reactive fiber/motif patterns.
    - Older NDS note features to validate:
      * ₱20: Manuel L. Quezon front, Banaue Rice Terraces reverse, older serial format, and legacy NDS color palette.
      * ₱50: Sergio Osmeña front, earlier reverse with Taal Lake/fish motif, and the older security thread/watermark style.
      * ₱100: original Roxas front and earlier reverse layout, proper NDS watermark portrait and serial styling.
      * ₱200: older Macapagal front and legacy reverse landmark design, with era-appropriate embedded thread and watermark.
      * ₱500: older Aquino-era portrait front and earlier reverse layout in the valid NDS design.
      * ₱1000: hero trio front and older reverse composition matching the legacy series design.
    - Forged notes often use simulated or surface-printed features: flat foil-like patches, printed threads, ink-only watermark effects, soft/blurry microtext, wrong color registration, mismatched serial styling, and weak or incorrect UV response.
    Use currency_analysis when multiple security features are present but fail quality, physical embedding, optical behavior (tilt/light/UV), or consistency tests. Do not default to genuine just because "security features are visible".
    """,

    "no_forgery_detected": """
    no_forgery_detected - Document looks authentic. Strong preference when expected genuine features are present and well-executed:
    - Correct government/university/school logos and headers
    - Physical embossed or holographic seals (raised texture, paper deformation, reflective properties)
    - Proper serial numbers, LRN (12 digits), Special Orders, reference numbers
    - Signatures with correct printed titles (e.g. Punongguro/Principal + Board Chairman; Regional Director with CESO title)
    - Verification features (QR + www.ltfrb.gov.ph/verify, BIR form numbers, red municipal seals on CTCs)
    - Natural ink/paper interaction and bilingual formatting where required
    - Consistent layout matching known genuine templates for that exact document type (BIR 0016 CTC, LTFRB CC, DepEd SHS diploma, FEU-style university diploma, etc.)
    - For currency: valid banknote design, correct portrait and denomination, watermark area, thread/window position, and expected security pattern are stronger than poor image quality or worn appearance.
    - Do not classify a note as counterfeit solely because the photograph is blurry, poorly lit, or shows a folded/creased genuine note.
    Only override to a forgery category when clear contradictory tampering evidence exists.
    """,

    "not_a_document": """
    not_a_document - Image is not a document. This includes selfies, memes, screenshots, object photos, packaging, labels, posters, receipts without valid document structure, or any non-paper item that is not an identity document, certificate, form, or legal paper.
    If the image shows an object, product, scene, or item that is clearly not a physical document, classify it as not_a_document. AI-visible non-document cues such as phone screens, billboards, receipts with no valid form structure, or unrelated objects should be placed here.
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

QUICK TRIAGE HINT: These top-3 categories are the most likely candidates based on a fast preliminary classification.

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


def _build_detailed_prompt(top3: list[str], user_context_block: str = "") -> str:
    """Build a focused Stage 2 prompt from the top-3 triage categories."""
    if not top3:
        return SYSTEM_PROMPT + user_context_block

    category_descriptions = []
    for category in top3:
        detail = CATEGORY_DETAIL.get(category)
        if detail:
            category_descriptions.append(detail.strip())
        else:
            category_descriptions.append(
                f"{category} - {CATEGORY_LABELS.get(category, category)}"
            )

    prompt = DETAILED_PROMPT_TEMPLATE.format(
        category_descriptions="\n\n".join(category_descriptions)
    )
    if user_context_block:
        prompt += "\n\n" + user_context_block
    return prompt


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


def _normalize_hint_text(text: Optional[str]) -> str:
    if not text:
        return ""
    text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    return any(
        lowered.startswith(prefix)
        for prefix in (
            "document type",
            "genuine or forged",
            "result",
            "verdict",
            "authenticity",
            "forgery category",
            "category",
            "confidence level",
            "confidence",
            "key evidence",
            "evidence",
            "brief reasoning",
            "reasoning",
            "summary",
            "conclusion",
            "document analysis",
        )
    )


def _extract_pasted_analysis_hints(text: Optional[str]) -> list[str]:
    """Parse report-style pasted analysis snippets into structured hints for the model."""
    raw = _normalize_hint_text(text)
    if not raw:
        return []

    lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
    hints: list[str] = []
    lower = raw.lower()

    if "document analysis" in lower:
        hints.append("The user pasted a document-analysis summary. Treat it as a weak hint, not a confirmed fact.")

    def extract_label_value(labels: tuple[str, ...]) -> Optional[str]:
        for idx, line in enumerate(lines):
            lowered = line.lower()
            for label in labels:
                if lowered.startswith(label):
                    value = line.split(":", 1)[1].strip() if ":" in line else ""
                    if value:
                        return value
                    for nxt in lines[idx + 1 : idx + 3]:
                        if not nxt:
                            continue
                        if _is_heading(nxt):
                            break
                        if nxt.startswith(("-", "*", "•", "1.", "2.", "3.", "4.", "5.")):
                            continue
                        return nxt.strip(" -•")
        return None

    doc_type = extract_label_value(("document type",))
    if doc_type:
        hints.append(f"Document type appears to be: {doc_type}")

    verdict = extract_label_value(("genuine or forged", "result", "verdict", "authenticity"))
    if verdict:
        hints.append(f"The pasted analysis classifies the document as: {verdict}")

    category = extract_label_value(("forgery category", "category"))
    if category and category.lower() not in {"none", "null", "n/a", "no forgery detected"}:
        hints.append(f"The pasted analysis suggests forgery category: {category}")

    confidence = extract_label_value(("confidence level", "confidence"))
    if confidence:
        hints.append(f"The pasted analysis reports confidence level: {confidence}")

    for idx, line in enumerate(lines):
        lowered = line.lower()
        if lowered.startswith(("key evidence", "evidence")):
            evidence_items: list[str] = []
            for nxt in lines[idx + 1 :]:
                if _is_heading(nxt):
                    break
                item = nxt.strip(" -•")
                if re.match(r"^(?:[-*•]|\d+\.)\s+", nxt):
                    evidence_items.append(re.sub(r"^(?:[-*•]|\d+\.)\s+", "", nxt).strip())
                elif item and len(item.split()) <= 20 and evidence_items:
                    evidence_items.append(item)
                elif item and len(item.split()) <= 10 and not evidence_items:
                    evidence_items.append(item)
            if evidence_items:
                hints.append("Evidence cues from the pasted analysis: " + "; ".join(evidence_items[:4]))
                break

    return hints


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
            "opaque_pigment_cover": "marker/paint covering text",
            "counterfeit_currency": "suspect counterfeit banknote",
            "computer_generated": "looks computer-generated / desktop-published",
            "scan_tampering_artifacts": "scanned document with visible digital edits layered on top",
            "sympathetic_hidden_writing": "hidden writing only visible under special lighting (UV, raking, backlight) - check for sympathetic_indented",
            "uv_reactive_ink_glow": "ink glows or reacts under UV light - check for sympathetic_special",
        }
        clue_label = _clue_labels.get(physical_clues, physical_clues.replace('_', ' '))
        lines.append(f"- Physical clue user thinks they observed: {clue_label}")

    parsed_hints = _extract_pasted_analysis_hints(suspicion_reason)
    if parsed_hints:
        lines.extend([f"- {hint}" for hint in parsed_hints])

    if suspicion_reason:
        clean = suspicion_reason.strip()[:300]
        if clean and clean.lower() not in {h.lower() for h in parsed_hints}:
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

    image = preprocess_image(image)
    user_context_block = _build_user_context_block(
        document_type, suspicion_reason, area_of_concern, image_source,
        is_forged_belief, shot_type, lighting, physical_clues,
    )

    top3 = [
        c for c in triage_classify(image, api_key=api_key).get("top_3", [])
        if c in CATEGORY_CODES
    ][:3]

    if system_prompt_override:
        prompt = system_prompt_override
        if top3:
            prompt += (
                "\n\nQUICK TRIAGE TOP-3 CANDIDATES: "
                + ", ".join(top3)
                + ". Focus on these categories unless the image strongly supports another type."
            )
        prompt += user_context_block
    else:
        prompt = _build_detailed_prompt(top3, user_context_block)

    buf = io.BytesIO()
    img_to_send = image if image.mode == "RGB" else image.convert("RGB")
    img_to_send.save(buf, format="JPEG", quality=88)
    buf.seek(0)

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

    critique = confidence_gated_analyze(
        image=image,
        _unused_ctx={},
        primary=result,
        user_context=user_context_block,
        threshold=0.80,
        api_key=api_key,
    )
    final_result = critique.get("result", result)
    final_result["model_used"] = model_used
    if critique.get("path"):
        final_result["_analysis_path"] = critique["path"]
    if critique.get("tokens_estimate") is not None:
        final_result["_tokens_estimate"] = critique["tokens_estimate"]
    return final_result


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
    "obliteration_pigment": "obliteration",
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
        ("obliteration_ink", "obliteration_pigment", "Both use covering material. Minimal prompt detail."),
        ("obliteration_whiteout", "obliteration_pigment", "Whiteout is white correction fluid; pigment is colored marker/paint."),
    ]
    existing = {(o["source"], o["target"]) for o in overlaps} | {(o["target"], o["source"]) for o in overlaps}
    for src, tgt, reason in semantic:
        if (src, tgt) not in existing and (tgt, src) not in existing:
            overlaps.append({"source": src, "target": tgt, "reason": reason, "from_prompt": False})
    aux_prompts = [
        {"name": "SYSTEM_PROMPT", "purpose": "Main 19-category classification (full pass)", "word_count": _prompt_word_count(system), "char_count": len(system)},
        {"name": "TRIAGE_PROMPT", "purpose": "Stage 1 quick top-3 classification (~$0.00005)", "word_count": _prompt_word_count(TRIAGE_PROMPT), "char_count": len(TRIAGE_PROMPT)},
        {"name": "DETAILED_PROMPT_TEMPLATE", "purpose": "Stage 2 narrowed prompt (currently unused - kept for experiments)", "word_count": _prompt_word_count(DETAILED_PROMPT_TEMPLATE), "char_count": len(DETAILED_PROMPT_TEMPLATE)},
        {"name": "CRITIQUE_PROMPT_TEMPLATE", "purpose": "Stage 3 self-critique when confidence < 0.80", "word_count": _prompt_word_count(CRITIQUE_PROMPT_TEMPLATE), "char_count": len(CRITIQUE_PROMPT_TEMPLATE)},
    ]
    rules = _extract_branching_rules(system)
    variables = _extract_user_variables(system)
    
    # Calculate current metrics
    current_words = _prompt_word_count(system)
    current_chars = len(system)
    
    # Calculate optimized metrics (35% reduction after externalization + consolidation)
    optimized_reduction_factor = 0.65  # Keep 65% of current content
    optimized_words = int(current_words * optimized_reduction_factor)
    optimized_chars = int(current_chars * optimized_reduction_factor)
    
    # API cost estimation (using Gemini 2.5 pricing: $0.075 per 1M input tokens, ~4 chars per token)
    tokens_per_call_current = current_chars // 4
    tokens_per_call_optimized = optimized_chars // 4
    cost_per_call_current = (tokens_per_call_current / 1_000_000) * 0.075
    cost_per_call_optimized = (tokens_per_call_optimized / 1_000_000) * 0.075
    cost_savings_per_call = cost_per_call_current - cost_per_call_optimized
    
    return {
        "system_prompt": {
            "current": {
                "total_words": current_words,
                "total_chars": current_chars,
                "estimated_tokens": tokens_per_call_current,
                "estimated_cost_per_call": round(cost_per_call_current, 5),
            },
            "optimized": {
                "total_words": optimized_words,
                "total_chars": optimized_chars,
                "estimated_tokens": tokens_per_call_optimized,
                "estimated_cost_per_call": round(cost_per_call_optimized, 5),
                "reduction_factor": "35%",
            },
            "potential_savings": {
                "per_call": round(cost_savings_per_call, 5),
                "per_1k_calls": round(cost_savings_per_call * 1000, 2),
                "per_1m_calls": round(cost_savings_per_call * 1_000_000, 0),
            },
            "optimization_strategy": "Externalize generic category prose to reference docs; consolidate redundant rules; keep Philippine-specific GENUINE DOCUMENT VERIFICATION (~2000 lines) intact for competitive advantage.",
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
