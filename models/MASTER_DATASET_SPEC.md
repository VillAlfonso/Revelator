# Master Dataset Specification — All 16 Categories

This is the across-the-board plan for getting Revelator from "demo with one
working category" to "16 working categories." Each category section is
self-contained: read the one you want to work on, ignore the rest.

The earlier `digital_cut_paste/DATASET_SPEC.md` is the deep-dive for that
single category. This document is the wider plan covering the other 15,
plus a refresher on cut-paste at a higher level so you can compare apples
to apples.

---

## How to read this document

Each category section is structured the same way:

| Field | What it tells you |
|---|---|
| **What it is** | Plain-language description of the forgery |
| **Visual signs** | What the eye (and the model) should look for |
| **Difficulty tier** | 1 = easy, 3 = hard; tackle in tier order |
| **Real samples needed** | How many genuine forgery photos to collect/create yourself |
| **Synth multiplier** | How many synthesized variants `synthesize.py` (or a per-category script) can produce per real sample |
| **Negatives needed** | How many clean documents (no forgery) for this category |
| **Forged : Negative ratio** | Target balance in the training set |
| **Equipment** | Specific gear — much of it cheap, some optional |
| **Where to source samples** | Existing datasets / image search terms / DIY notes |
| **Synthesize.py applicable?** | Whether the existing script (or a small extension) can generate fakes for this category |

At the end there's a **master numbers table**, an **equipment shopping list**,
and a **suggested order of execution**.

---

## The shared base layer (build once, reuse for all 16 categories)

Before any category-specific work: you need a pool of **clean, unaltered
documents**. The same pool is reused as:

- The "donor" images for `synthesize.py`'s digital splicing
- The negatives (empty-label samples) for every category
- The substrate you'll print on to create physical forgeries

**Target: 500–1,500 unique clean documents.**

Get most of these for free from the public datasets we already wired up
(`scripts/fetch_sources.py`). Add 50–100 photographs of your own
documents (Filipino-context relevance: PSA forms, BIR returns, school
diplomas, IDs, receipts). Keep them in `sources/` at the repo root.

This pool serves every one of the 16 categories. Spend a real hour on
this and the rest of the project goes faster.

---

## Equipment shopping list (one-time)

Most of this is under PHP 2,000 / USD 35 total. Yes to the UV flashlight.

| Item | Purpose | Cost (PHP) | Required for |
|---|---|---|---|
| **UV flashlight (365nm preferred)** | Reveals security features, sympathetic ink | ~PHP 200–500 | sympathetic_special, currency_analysis |
| **Carbon paper (pack of 25)** | Carbon-transfer forgery creation | ~PHP 50 | traced_carbon |
| **White-out / Liquid Paper** | Whiteout obliteration creation | ~PHP 60 | obliteration_whiteout |
| **Ink eraser pen (Pilot Frixion or similar)** | Chemical erasure | ~PHP 100 | erasure_chemical |
| **Rubbing alcohol 70% (small bottle)** | Alternate chemical erasure | ~PHP 50 | erasure_chemical |
| **Cotton swabs / Q-tips** | Apply chemicals precisely | ~PHP 30 | erasure_chemical |
| **Mixed pen set (ballpoint, gel, marker, fine-tip)** | Variation in additions/insertions | ~PHP 200 | additions, obliteration |
| **Sharpie / permanent marker** | Ink obliteration | ~PHP 50 | obliteration_ink |
| **Acrylic paint (small black + small colored)** | Pigment obliteration | ~PHP 100 | obliteration_pigment |
| **Cheap sandpaper / utility knife** | Mechanical erasure | ~PHP 40 | erasure_mechanical |
| **Eraser block (rubber)** | Mechanical erasure | ~PHP 20 | erasure_mechanical |
| **Phone tripod + small lamp / flashlight** | Oblique-light photography | ~PHP 300 | sympathetic_indented, traced_indentation |
| **Real Philippine peso (full set ₱20–₱1000)** | Currency dataset baseline | PHP 5,720 (face value) | currency_analysis |
| **Plain bond paper, A4, 80gsm (1 ream)** | Substrate for everything | ~PHP 250 | All physical categories |
| **Printer (you likely have one)** | Print clean docs to alter | — | All physical categories |
| **Phone with decent camera (≥12MP)** | Capture | — | Everything |

**Total out-of-pocket:** roughly PHP 7,000 (~USD 130) including currency
face value (which you keep). Without the currency: ~PHP 1,500 (~USD 27).

You don't need a "real" forensic UV cabinet, IR camera, or microscope —
those are the next price tier and not worth it for a capstone. Phone
camera + good lighting + cheap chemicals handles this.

---

## Difficulty tiers

Work through these in order. Tier 1 categories are achievable in a long
weekend. Tier 3 will take longer and may need scoping down depending on
your defense timeline.

| Tier | Categories | Why |
|---|---|---|
| **1 — Easy** | digital_cut_paste, digital_desktop, addition_insertion, addition_interlineation, obliteration_whiteout | Either fully synthesizable (digital) or trivial DIY with cheap supplies |
| **2 — Medium** | obliteration_ink, obliteration_pigment, erasure_mechanical, erasure_chemical, digital_scanned | DIY with slightly more setup; consistent results |
| **3 — Hard** | traced_carbon, traced_indentation, traced_projection, sympathetic_indented, sympathetic_special, currency_analysis | Need specific equipment / lighting; harder to make clean labeled samples |

---

# DIGITAL CATEGORIES (Tier 1 — easiest, fully or mostly synthesizable)

## 1. `digital_cut_paste` — Cut and Paste

**Status:** Fully covered in `models/digital_cut_paste/DATASET_SPEC.md`.
TL;DR for completeness in this master doc:

- **Real samples needed:** 36 already have (Roboflow handcrafted, in valid+test).
- **Synth multiplier:** 12–15× per source via `synthesize.py`.
- **Sources needed:** 300 clean documents.
- **Negatives needed:** ~1,800.
- **Forged : Negative ratio:** ~70 : 30.
- **Synthesize.py:** YES, fully covered.

---

## 2. `digital_desktop` — Desktop Publishing

**What it is:** Someone fabricates a fake document from scratch using
software (Word, Canva, Photoshop). Common targets: fake IDs, fake
certificates, fake bills, fake receipts. This is the most common
"fully fabricated" forgery.

**Visual signs the model learns:**

- Fonts that don't match the official template (slightly wrong typeface)
- Inconsistent text alignment / spacing
- Wrong color shades (close but not exact)
- Missing or wrong-positioned security elements (logos, holograms, seals)
- Print-from-screen artifacts (slightly visible pixel grid in lines)

**Difficulty tier:** 1.

**Real samples needed:** 50–80. Each is a fake document you create in
Word/Canva. They should look "good enough to fool a casual reviewer"
but have small mistakes. Save with mixed JPEG quality (60, 75, 90) to
mimic save-and-share behavior.

**Synth multiplier:** 4–6×. The same fake template, exported at
different qualities and with small font/color tweaks, multiplies it
quickly without you redrawing.

**Negatives needed:** 200–400. Your shared base pool (real PSA forms,
real receipts, real IDs) provides these. The model needs to see
**a lot** of real official-looking documents so it doesn't hallucinate
"fake" on the real ones.

**Forged : Negative ratio:** 30 : 70 (heavy on negatives because the
hardest case is keeping false-positives off real official docs).

**Equipment:** Word / Canva / Photoshop. Optional: a printer to print
some fakes for re-photographing (catches the "print → photograph" path).

**Where to source samples:**

- DIY: search "blank [PSA / BIR / school certificate] template" online,
  fill out the blanks with fake data, save as JPG.
- Real official-document references: government websites publish blank
  PDF templates of their forms. Render those to JPG as your negatives.
- Roboflow Universe: search "fake ID detection" or "ID forgery" — a
  few small datasets exist. Treat as supplementary, not primary.

**Synthesize.py applicable?** PARTIAL. Current script is splice-only.
A small extension could swap fonts on regions of a real document to
simulate typo-style fabrication, but it's lower-priority than
collecting real fakes. Skip for now.

**Variance to cover:**

- Document type (IDs, certificates, receipts, bills, contracts)
- Capture (saved-as-PNG, screenshot, photographed-from-screen, scanned-print)
- "Fake quality" (obvious fake, near-perfect fake)
- Languages (English, Filipino, mixed)

---

## 3. `addition_insertion` — Addition: Insertion

**What it is:** Adding new characters or digits **within** existing text
to change its meaning. Classic example: turning "$100" into "$1,000"
by inserting digits, or adding "not" into a contract clause.

**Visual signs:**

- Character spacing is unusual (cramped where the new thing was inserted)
- New ink color/shade slightly different from surrounding ink
- Sometimes the inserted character is a different size or font weight
- Pen pressure / line thickness varies on the inserted parts

**Difficulty tier:** 1.

**Real samples needed:** 50–80. Print short text passages, then add
characters with different pens. Vary pen types (ballpoint, gel,
fine-liner) and vary how cleanly you insert.

**Synth multiplier:** 6–8× via lighting/contrast augmentation. A
synthesizer extension could digitally insert characters on real
documents — that would be a 20×+ multiplier — but only if the model
will see digital insertions in the wild. Most insertion forgery is
ink-on-paper, so DIY photos are higher signal.

**Negatives needed:** 200–300. Clean text-heavy documents (contracts,
receipts, forms with hand-written text already on them).

**Forged : Negative ratio:** 60 : 40.

**Equipment:**

- Printed documents (use templates from the shared base pool)
- 4–6 pens of different ink colors, types
- Phone camera

**Where to source samples:**

- DIY only. This category is too specific for public datasets.
- Idea: use the same 30 base documents and create 2–3 insertions on
  each, photographing each insertion separately.

**Synthesize.py applicable?** PARTIAL. A future extension that overlays
small text snippets at random positions in existing text regions would
work — call it `--insertion` mode. Lower priority than DIY photos.

**Variance to cover:**

- Pen color (black, blue, occasionally other)
- Pen type (ballpoint, gel, marker)
- Insertion size (1 character, 1 word, multiple words)
- Position (start of word, middle, end of line)
- Document type (forms with handwritten fields, all-print contracts, mixed)
- Lighting (overhead office, dim, harsh, side-lit)

---

## 4. `addition_interlineation` — Addition: Interlineation

**What it is:** Adding new writing **between existing lines** of a
document — squeezing a clause "or any of his heirs" into the gap
between two contract lines, for instance. Distinct from insertion
because the new content sits in white space rather than within
existing text.

**Visual signs:**

- Cramped writing in line gaps (not enough room → small/squished)
- Different ink than surrounding lines
- Sometimes tilted (forger had to tilt the pen to fit)
- Page may show indentation / paper deformation from the writing pressure

**Difficulty tier:** 1.

**Real samples needed:** 50–80. Same DIY workflow as insertion but
target gaps between lines. Use single-spaced documents so the gaps are
small and the cramping is realistic.

**Synth multiplier:** 6–8×.

**Negatives needed:** 200–300. Single-spaced, multi-line documents
(contracts, letters) — the same pool you'd otherwise use for
insertion negatives.

**Forged : Negative ratio:** 60 : 40.

**Equipment:** Same as insertion.

**Where to source samples:**

- DIY only.
- Tip: use printouts of public-domain contracts (Project Gutenberg has
  some), Filipino legal templates, or just generate Lorem-ipsum filled
  contract layouts in Word.

**Synthesize.py applicable?** PARTIAL via the same `--insertion`
extension as above, with the constraint that overlay text lands in the
inter-line gap rather than within text.

**Variance to cover:**

- Gap size (tight to comfortable)
- Length of insertion (single word vs full clause)
- Pen type and ink
- Pressure (clear writing vs cramped scribble)

---

## 5. `obliteration_whiteout` — White Out

**What it is:** Using correction fluid (Tipp-Ex, Liquid Paper) to cover
existing text, then writing or printing new text on top.

**Visual signs:**

- White raised area different from paper texture (correction fluid has a
  slight thickness and matte sheen)
- Edges of the white-out are usually irregular, not perfectly rectangular
- New text on top may sit slightly above or be a different font
- Under raking light, the topology change is visible

**Difficulty tier:** 1.

**Real samples needed:** 50–80. DIY: print short text, white out a
word or number, write new content over it. Photograph from multiple
angles.

**Synth multiplier:** 8–10×. White-out is texturally consistent enough
that lighting variations + crops produce many useful training images
from one physical sample.

**Negatives needed:** 200–300. Importantly, include documents with
**legitimate** corrections — places where someone genuinely corrected
a mistake. Also include documents with stamps and seals (which can
texturally resemble white-out under bad lighting). These are the
hardest negatives — the model must learn that rectangular off-white
patches aren't always forgeries.

**Forged : Negative ratio:** 50 : 50 (heavier than other categories on
negatives because the hard-negative class is so important here).

**Equipment:**

- White-out / Liquid Paper / Tipp-Ex (PHP 60–100, any office supplies
  store)
- Pens for writing replacement text
- Phone camera

**Where to source samples:**

- DIY primary.
- Roboflow Universe: search "whiteout document" — small but exists.

**Synthesize.py applicable?** PARTIAL. A future extension could draw
white rectangles on text regions then render new text on top. Call it
`--whiteout` mode. Lower priority than DIY because the texture of real
correction fluid is part of the signal.

**Variance to cover:**

- Coverage size (one word, one line, paragraph)
- Replacement text (handwritten vs printed)
- Lighting (especially raking/oblique light, where white-out shows
  topology)
- Document age and quality

---

# PHYSICAL ALTERATION CATEGORIES (Tier 2)

## 6. `obliteration_ink` — Ink Stroke Obliteration

**What it is:** Crossing out / scribbling over original text with a
thick line of ink — a "redacted" look. Often used to hide an
original number or name.

**Visual signs:**

- Thick dark area covering text
- Original text often **partially visible** at the edges or under the
  ink (especially with infrared, but also with strong overhead light)
- Ink color and gloss differ from the underlying document's printing

**Difficulty tier:** 2.

**Real samples needed:** 50–80. DIY: print text, scribble over with
markers of various widths.

**Synth multiplier:** 6–8×. Lighting and crop variations on the same
real sample work fine.

**Negatives needed:** 200–300. Include documents with **legitimate
redactions** (government docs sometimes have black bars), stamped
documents, and signatures over text — all easy false positives.

**Forged : Negative ratio:** 60 : 40.

**Equipment:**

- Sharpie / black gel pen / black ballpoint
- Optionally: colored markers for variety

**Where to source samples:**

- DIY primary.
- Public dataset hint: "redacted document" image search returns plenty
  of inspiration; many genuine redactions can serve as hard negatives.

**Synthesize.py applicable?** PARTIAL. An extension could draw filled
black rectangles or freehand-shaped polygons over text regions.
Implementation is moderate effort (~1 hour) and produces a
proportionally large variety of training examples. Worth doing if you
want to scale this category fast.

**Variance to cover:**

- Marker thickness (thin pen → thick Sharpie)
- Coverage shape (straight crossout, scribble, thick rectangle)
- Color (black is most common; include blue + dark red for variety)
- How many lines obliterated (single word vs paragraph)

---

## 7. `obliteration_pigment` — Opaque Pigment

**What it is:** Like ink obliteration but using thicker, more opaque
materials — paint, opaque markers, pigment-loaded correction tape.
The key difference from ink is **opacity**: pigment fully blocks
visibility of underlying text, ink obliteration usually has slight
transparency.

**Visual signs:**

- Solid block of color, often raised texture
- No visible underlying text (vs ink obliteration where ghost text peeks through)
- Color is typically uniform within the patch (paint/pigment is more uniform than ink)
- Sometimes brush strokes or applicator marks visible

**Difficulty tier:** 2.

**Real samples needed:** 30–60. DIY: cover text with acrylic paint,
opaque markers, or correction tape.

**Synth multiplier:** 6–8×.

**Negatives needed:** 100–200.

**Forged : Negative ratio:** 60 : 40.

**Equipment:**

- Cheap acrylic paint set
- Opaque markers (POSCA, Sharpie Oil-Based)
- Correction tape

**Where to source samples:** DIY primary.

**Synthesize.py applicable?** Same partial-yes as ink obliteration —
draw opaque polygons over text regions. Slightly different texture
parameters than ink (more uniform fill, no transparency).

**Variance to cover:** Color, opacity, brush vs roller vs marker.

---

## 8. `erasure_mechanical` — Mechanical Erasure

**What it is:** Physically removing ink/text using mechanical means —
rubber eraser, knife/blade scraping, sandpaper, fingernail scratching.

**Visual signs:**

- Paper fibers visibly disturbed (raised, fuzzy)
- Texture rough where erased
- Sometimes paper is thinner / slightly translucent in erased area
- Slight discoloration or yellowing
- Ghost text often partially visible

**Difficulty tier:** 2.

**Real samples needed:** 30–50. DIY: write with pencil or non-permanent
ink, erase aggressively. For ink documents, lightly scrape with a
blade.

**Synth multiplier:** 4–6×. Texture is harder to vary than ink — the
real signal is paper-fiber damage, which doesn't multiply well from
one sample.

**Negatives needed:** 100–200. Include slightly worn / aged documents
and folded paper edges as hard negatives.

**Forged : Negative ratio:** 60 : 40.

**Equipment:**

- Pencil + eraser (for pencil-erasure samples)
- Pens + utility knife (for ink-scrape samples)
- Rubber eraser block
- Sandpaper (very fine grit)

**Where to source samples:** DIY primary. Forensics textbooks have
example images you can use as visual reference for what "good erasure"
looks like (don't include in dataset — just use as guidance).

**Synthesize.py applicable?** NO — this is a paper-texture artifact,
not synthesizable from clean documents. Real photos are mandatory.

**Variance to cover:**

- Erasure tool (eraser, blade, sandpaper, fingernail)
- Aggressiveness (light cleanup vs heavy hole-through-paper)
- Paper type (cheap bond, glossy, recycled)
- Lighting (raking light shows fiber damage best)

---

## 9. `erasure_chemical` — Chemical Erasure

**What it is:** Using chemicals to dissolve / lift ink from paper.
Common consumer products: ink-eraser pens (often containing sodium
hydrosulfite or similar), rubbing alcohol, bleach. Industrial: stronger
solvents.

**Visual signs:**

- Paper texture damaged but in a different way than mechanical
  (chemical etching, not fiber tearing)
- Often a slight brown/yellow halo from chemical reaction
- Residual ghost ink (incomplete chemical removal)
- Under UV: chemical residue often fluoresces

**Difficulty tier:** 2.

**Real samples needed:** 30–50. DIY: write on paper with regular pen,
apply ink-eraser pen, photograph. Vary chemical type (Frixion-style ink
eraser, rubbing alcohol with cotton swab, dilute bleach).

**Synth multiplier:** 4–6×.

**Negatives needed:** 100–200. Hard negatives: water-stained documents
and coffee-stained documents are the closest false-positive class.

**Forged : Negative ratio:** 60 : 40.

**Equipment:**

- Ink eraser pens (multiple brands)
- Rubbing alcohol + cotton swabs
- Optional UV flashlight (chemical residue fluoresces — bonus signal)

**Where to source samples:** DIY primary.

**Synthesize.py applicable?** NO. Chemical artifacts are paper-level
and not reproducible synthetically.

**Variance to cover:**

- Chemical type
- Application method (precise pen vs broad swab)
- Original ink type (some inks resist chemicals better)
- Drying time / paper saturation
- Lighting (UV pass adds signal — see sympathetic_special)

---

## 10. `digital_scanned` — Scanned Documents

**What it is:** Forgery that's been printed, then scanned (or
photocopied) to hide the original digital tampering. The scan
itself isn't the forgery — it's a *masking step* over a forgery from
another category.

**Visual signs:**

- Generation-loss artifacts (each print-scan cycle degrades quality)
- Photocopy halftone patterns visible at high zoom
- Multiple JPEG compression generations leave specific frequency-domain marks
- Edges have a "softness" not seen in originals

**Difficulty tier:** 2 (because it's category-on-category — you need
forgeries from other categories to scan).

**Real samples needed:** 30–50. Take forged documents from your other
categories (especially digital_cut_paste, addition_insertion), print
them, photocopy or scan, and re-capture. That gives you the
"scan-of-forgery" sample set.

**Synth multiplier:** 8–10×. Cheap to vary because each scan-cycle
adds compounding artifacts.

**Negatives needed:** 200–300. **Important:** include lots of LEGITIMATE
scanned documents — real photocopies, real scans of unaltered originals.
This is the dominant false-positive class.

**Forged : Negative ratio:** 50 : 50 (because scan artifacts on
legitimate scanned docs are visually similar to scan artifacts on
forged docs — careful balance needed).

**Equipment:** Any scanner or photocopier. Phone camera works as a
"scan" surrogate (photograph documents flat under uniform light).

**Where to source samples:**

- For positives: print and scan your own forgeries from categories 1–9.
- For negatives: any scanned legitimate documents (RVL-CDIP is mostly
  this — those samples are scans of real documents).

**Synthesize.py applicable?** PARTIAL. An extension could simulate the
scan step: heavy multi-stage JPEG compression, halftone pattern overlay,
slight blur, contrast crush. That's a valuable extension because it
multiplies your dataset cheaply for this category specifically.

**Variance to cover:**

- Number of scan generations (1, 2, 3 — more cycles = more degradation)
- Scan resolution (low DPI vs high DPI)
- Photocopier vs flatbed scanner vs phone-camera "scan"
- Color vs grayscale scan

---

# TRACED-SIGNATURE CATEGORIES (Tier 3 — most niche)

## 11. `traced_carbon` — Carbon Transfer

**What it is:** Forger places carbon paper between an authentic signature
and a blank page, then traces over the original — so the carbon
transfers a faint copy onto the underneath sheet. The forger then
darkens the carbon copy with ink.

**Visual signs:**

- Lines are unusually smooth and consistent (no natural pen pressure
  variation)
- Slight broken / dotted character (carbon doesn't transfer perfectly
  uniform)
- Faint underlying carbon often visible alongside the over-traced ink
- Stroke speeds are too uniform — a real signature has fast and slow parts

**Difficulty tier:** 3.

**Real samples needed:** 30–50. DIY: trace your own signature with
carbon paper between two sheets, then ink over the carbon impression.

**Synth multiplier:** 4–6×.

**Negatives needed:** 100–200. Real signatures (genuine, hand-signed)
are the negative class.

**Forged : Negative ratio:** 50 : 50.

**Equipment:**

- Carbon paper (PHP 50 for a pack)
- Various pens
- Optional: collect signatures from family/team members (with
  permission) so each forgery has a different "real" donor signature

**Where to source samples:**

- DIY primary.
- Roboflow Universe: search "signature forgery" — limited but some
  exist.

**Synthesize.py applicable?** NO.

**Variance to cover:**

- Donor signature complexity (simple, ornate)
- Tracing pen type
- How heavy the tracing is (light vs over-darkened)
- Whether the carbon is fully covered or partially visible

---

## 12. `traced_indentation` — Indentation / Canal Light

**What it is:** Forger writes on top of a paper stack with hard pressure,
leaving an indented impression on the page below. They then trace the
impression with ink to create a copy. The grooves (indentations)
betray the forgery — the new ink fits perfectly into the canals.

**Visual signs:**

- Visible canal/groove lines under raking (low-angle) light
- The ink fills the indentation precisely, with minimal spillover
- Surrounding paper looks "pressed" — depression rings around the
  signature

**Difficulty tier:** 3 (mostly because of the lighting requirement).

**Real samples needed:** 30–50. DIY: stack 2 sheets, write hard with a
ballpoint on the top one, then trace over the indentations on the
bottom sheet with ink. Photograph **with a light from low angle** so
the canals cast shadows.

**Synth multiplier:** 4–6×.

**Negatives needed:** 100–200. Genuine signatures photographed under
the same raking-light setup (so the model doesn't learn "raking light
= forgery").

**Forged : Negative ratio:** 50 : 50.

**Equipment:**

- Two-sheet paper stack
- Pens (ballpoint for indentation, ink pen for tracing)
- **A side lamp or phone flashlight at low angle** — non-negotiable;
  this is the discriminator

**Where to source samples:** DIY primary. Forensic-document-examination
textbooks have example photos for visual reference (Hilton, Osborn).

**Synthesize.py applicable?** NO.

**Variance to cover:**

- Lighting angle (10°, 20°, 30° from horizontal)
- Indentation depth (light pressure → deep press)
- Tracing precision (sloppy fill vs careful)

---

## 13. `traced_projection` — Projection Process

**What it is:** Forger projects an image of an authentic document onto
a blank paper using a light source (overhead projector, lightbox, modern
DIY: phone flashlight under glass / window during day) and traces over
the projection.

**Visual signs:**

- Slight scaling differences vs the original (projection geometry is
  imperfect)
- Lines have faint glow or "ghosting" at edges (imperfect tracing
  registration)
- Stroke uniformity is unnaturally consistent
- Sometimes parallax distortion

**Difficulty tier:** 3.

**Real samples needed:** 30–50. DIY: tape a printed signature to a
window during daylight, place blank paper over it, trace through. Or
use a phone with flashlight under a glass-top desk.

**Synth multiplier:** 4–6×.

**Negatives needed:** 100–200.

**Forged : Negative ratio:** 50 : 50.

**Equipment:** Light source, glass surface, paper, pens.

**Where to source samples:** DIY primary.

**Synthesize.py applicable?** NO.

**Variance to cover:**

- Projection method (window, lightbox, phone-under-glass)
- Pen type for tracing
- Tracing precision

---

# SYMPATHETIC INK CATEGORIES (Tier 3 — UV required)

## 14. `sympathetic_indented` — Indented Writing (revealed)

**What it is:** Detection of the **shadow** of writing left on the
paper underneath the page that was written on. Used in forensics to
recover information from a missing page (think: police pad scene).
This isn't a forgery per se — it's a *recovery* technique. The model
learns to detect that there ARE indentations on a paper that has no
visible writing.

**Visual signs:**

- Paper appears blank under normal light
- Under raking (low-angle) light, faint impressions become visible as
  shadow lines

**Difficulty tier:** 3.

**Real samples needed:** 30–50. DIY: write on top sheet with hard
pressure, photograph the second sheet under raking light. Captures
should pair (a) the indented sheet under normal light, and (b) the
same sheet under raking light — but the model only sees one (the
raking-light version).

**Synth multiplier:** 4–6×.

**Negatives needed:** 100–200. Genuinely blank papers under raking
light, papers with paper-texture grain that could be mistaken for
indentations (cheap recycled paper has visible fiber patterns).

**Forged : Negative ratio:** 50 : 50.

**Equipment:**

- Pens for writing (pressure matters — ballpoint works well)
- Two sheets of paper
- Raking light source (lamp at low angle, smartphone flashlight at
  low angle)
- Phone tripod for steady captures

**Where to source samples:** DIY primary.

**Synthesize.py applicable?** NO.

**Variance to cover:**

- Pressure of original writing (light → heavy)
- Paper thickness (60gsm → 100gsm)
- Light angle
- Paper grain orientation

---

## 15. `sympathetic_special` — Special Ink (UV / Fluorescent)

**What it is:** Ink that's invisible or barely visible under normal
light but fluoresces strongly under UV. Used legitimately in security
documents (passports, currency, passes), and used in fraud (to add
secret annotations or alter UV-active features).

**Visual signs:**

- Under UV: glowing colored regions, often blue/green/red
- Under normal light: nothing or minimal evidence

**Difficulty tier:** 3 — requires UV flashlight.

**Real samples needed:** 30–50 paired captures. Each pair is the same
document under (a) normal light and (b) UV. The dataset should include
both halves so the model can learn the relationship.

**Synth multiplier:** 4–6×. Lighting variations on the same UV
capture multiply the training set.

**Negatives needed:** 100–200. **Critical:** include legitimate
UV-active documents (genuine bank notes, passports if you have one,
some receipts, security paper). The model must NOT learn "UV
fluorescence = forgery."

**Forged : Negative ratio:** 40 : 60 (heavier on negatives because the
real-UV-active-feature class is huge and important).

**Equipment:**

- **UV flashlight (365nm preferred)** — buy this. PHP 200–500 on Shopee
  or Lazada. Search "UV flashlight 365nm currency check" — they sell
  these for fake-bill detection, perfect for our use.
- UV pens / invisible ink pens — PHP 100, also on Shopee
- Documents with UV features (Philippine peso bills, your passport if
  applicable)

**Where to source samples:**

- DIY primary, both for positives (you mark documents with UV pen) and
  negatives (you photograph genuine UV-active features on real docs).
- Wikipedia has reference images of UV-fluorescent currency features
  (search "[currency name] UV features").

**Synthesize.py applicable?** NO. UV imaging is its own optical
modality.

**Variance to cover:**

- UV wavelength (365nm vs 395nm — 365 is "true" UV, 395 is purplish)
- Ambient light leakage (perfect dark vs slight ambient)
- UV flashlight distance / angle
- Document type (currency, passport, plain paper with UV pen)

**Tip:** since you need a UV flashlight for currency_analysis anyway,
buy one nicer flashlight that handles both — a 365nm with a small UV
filter. The cheaper "blacklight" ones at 395nm work for currency but
miss some forensic features.

---

# SPECIAL CATEGORY (Tier 3, but the headline use case)

## 16. `currency_analysis` — Currency Forgery

**What it is:** Detecting counterfeit banknotes vs genuine ones. Real
currency has many security features: watermarks, security threads,
microprinting, intaglio printing (raised ink), color-shifting elements,
UV-fluorescent areas, and specific texture/feel.

**Visual signs (genuine):**

- Watermark visible when held to light
- Embedded security thread (look like a dashed line under reflected
  light, solid line transmitted)
- Microprinting (text so small it requires magnification)
- Color-shifting ink on certain elements
- UV-fluorescent serial number / hidden features

**Visual signs (counterfeit):**

- Watermark printed (rather than embedded) — looks different at angles
- No security thread, or printed-on imitation
- Microprinting blurry or wrong text
- Wrong UV response (most common tell)
- Paper feel wrong (real currency is a cotton-linen blend, not paper)

**Difficulty tier:** 3.

**Real samples needed:** This category is unusual:

- **Photograph 20–40 GENUINE notes** of each denomination
  (₱20/₱50/₱100/₱200/₱500/₱1000) under multiple lighting conditions:
  normal, raking, UV, transmission (held to bright light).
- **For counterfeits:** legally getting actual counterfeits is hard.
  **Alternative:** photograph "novelty money" / "movie prop money" —
  these are intentionally non-functional but visually resemble real
  currency. Available online for cheap. Also: photograph real money
  that's been damaged, faded, or worn, which catches similar features
  to counterfeit detection.

**A safer scoping option:** Reframe this category as **"verify
authenticity features"** rather than "detect counterfeits." The model
detects PRESENCE of expected features (watermark, security thread,
UV fluorescence in the right spot) and flags absence. This is what
real currency-verification machines do.

**Synth multiplier:** 6–8× per genuine note (multiple lighting per
note → many training images).

**Negatives needed:** 50–100. "Negatives" here means "non-currency"
(receipts, IDs, certificates). The model should NOT activate on
non-currency.

**Forged : Genuine : Negative ratio:** 30 : 50 : 20. Three-way split
because there are three classes, not two.

**Equipment:**

- Real Philippine peso bills (full denomination set)
- Optional: novelty money for "obvious counterfeit" examples
- UV flashlight (overlap with `sympathetic_special`)
- Phone tripod for consistent lighting
- Black backdrop for clean captures
- Optional: lightbox for transmission shots (held-to-light watermark
  visibility)

**Where to source samples:**

- Real bills: your wallet
- Reference for genuine features: Bangko Sentral ng Pilipinas website
  has detailed security-feature documentation per denomination —
  https://www.bsp.gov.ph (search "security features banknotes")
- Novelty money: Lazada / Shopee — search "prop money fake"
- Roboflow Universe: search "currency detection" — many open datasets,
  mostly for denomination-counting rather than counterfeit-detection,
  but useful as negative class.

**Synthesize.py applicable?** NO. Currency forgery detection requires
real photographs.

**Variance to cover:**

- Denomination (all 6 PH peso bills)
- Wear level (crisp new, slightly worn, very worn)
- Lighting (normal, raking, UV, transmission)
- Angle / tilt (security features show only at specific angles)
- Background (table, hand, dark backdrop)

---

# Master numbers table

What "the full dataset" actually adds up to. Real samples = photos you
take or generate. Synth output = produced via `synthesize.py` or
category-specific extensions. Negatives = clean / non-forged samples
the model also sees.

| # | Category | Tier | Real samples | Synth multiplier | Synth output | Negatives | **Total dataset** |
|---|---|:-:|---:|:-:|---:|---:|---:|
| 1 | digital_cut_paste | 1 | (none — uses sources) | 12–15× × 300 sources | ~4,500 | 1,800 | **~6,300** |
| 2 | digital_desktop | 1 | 50–80 | 4–6× | ~280 | 200–400 | **~600** |
| 3 | addition_insertion | 1 | 50–80 | 6–8× | ~480 | 200–300 | **~830** |
| 4 | addition_interlineation | 1 | 50–80 | 6–8× | ~480 | 200–300 | **~830** |
| 5 | obliteration_whiteout | 1 | 50–80 | 8–10× | ~640 | 200–300 | **~990** |
| 6 | obliteration_ink | 2 | 50–80 | 6–8× | ~480 | 200–300 | **~830** |
| 7 | obliteration_pigment | 2 | 30–60 | 6–8× | ~360 | 100–200 | **~570** |
| 8 | erasure_mechanical | 2 | 30–50 | 4–6× | ~200 | 100–200 | **~400** |
| 9 | erasure_chemical | 2 | 30–50 | 4–6× | ~200 | 100–200 | **~400** |
| 10 | digital_scanned | 2 | 30–50 | 8–10× | ~400 | 200–300 | **~700** |
| 11 | traced_carbon | 3 | 30–50 | 4–6× | ~200 | 100–200 | **~400** |
| 12 | traced_indentation | 3 | 30–50 | 4–6× | ~200 | 100–200 | **~400** |
| 13 | traced_projection | 3 | 30–50 | 4–6× | ~200 | 100–200 | **~400** |
| 14 | sympathetic_indented | 3 | 30–50 | 4–6× | ~200 | 100–200 | **~400** |
| 15 | sympathetic_special | 3 | 30–50 (paired) | 4–6× | ~200 | 100–200 | **~400** |
| 16 | currency_analysis | 3 | 20–40 per denom × 6 = ~150 | 6–8× | ~1,000 | 50–100 | **~1,250** |
| **TOTALS** | | | **~720 real photos** | | **~10,000 synth** | **~3,800 negatives** | **~14,700 total** |

So the **physical lift** is roughly 720 photos plus the digital_cut_paste
sourcing you've already done. ~720 photos is one to two weekends of
actual capture work if you batch by category (do all the white-out
samples in one sitting, all the ink obliteration in another, etc.).

---

# Forged-to-Negative ratios — quick reference

The right ratio differs per category based on how easily false
positives happen on legitimate-looking documents:

| Ratio | Categories | Why |
|---|---|---|
| **70 : 30** | digital_cut_paste | Plenty of synthesizable positives; less risk on FP |
| **60 : 40** | most physical and addition categories | Standard balance |
| **50 : 50** | obliteration_whiteout, obliteration_ink, traced_*, digital_scanned, sympathetic_indented | Hard-negative class is large (legitimate corrections, redactions, raking-light captures) |
| **40 : 60** | sympathetic_special | Real UV-active features are everywhere; FP is the dominant risk |
| **30 : 70** | digital_desktop | Real official documents must dominate so fakes don't trigger on real ones |
| **30 : 50 : 20** (3-class) | currency_analysis | Counterfeit / genuine / non-currency split |

---

# Equipment shopping list (consolidated)

Buy in this order — earlier items unlock more categories per peso spent.

1. **Plain bond paper, A4, 80gsm** (PHP 250 / ream)
2. **Mixed pen set** (PHP 200) — ballpoint, gel, marker, fine-tip
3. **White-out / Tipp-Ex** (PHP 60)
4. **Sharpie + colored markers** (PHP 100)
5. **Carbon paper pack** (PHP 50)
6. **Eraser block + cheap utility knife** (PHP 60)
7. **Ink eraser pen + rubbing alcohol + cotton swabs** (PHP 180)
8. **Acrylic paint set, small** (PHP 100)
9. **Cheap phone tripod + small lamp** (PHP 300)
10. **UV flashlight, 365nm** (PHP 200–500) — last because it covers two categories
11. **Real Philippine peso, full set ₱20–₱1000** (PHP 5,720 face value, kept) — for currency_analysis only

**Total physical investment (excluding currency):** ~PHP 1,500.
**With currency:** ~PHP 7,200, but the bills retain their value.

---

# Suggested order of execution

A practical 4-week plan if you want to ship all 16 categories. Adjust
to your timeline.

### Week 1 — Foundation

- Run `scripts/fetch_sources.py --n 1500` to populate the shared base
- Photograph 50 personal documents (receipts, forms, IDs) for local
  variance
- Buy the equipment shopping list (skip currency for now)
- **Output:** 1,550 clean source documents in `sources/`

### Week 2 — Tier 1 categories (5 categories)

- One evening per category, ~50–80 forgeries each
- Run `synthesize.py` extensions where applicable (digital_cut_paste,
  the additions)
- **Output:** ~3,000 training samples for the easy 5

### Week 3 — Tier 2 categories (5 categories)

- More physical work — set aside 1–2 evenings per category
- erasure_mechanical and erasure_chemical can be done in one sitting
  using the same source documents
- **Output:** ~2,500 more training samples

### Week 4 — Tier 3 categories (6 categories)

- Buy UV flashlight + currency, set aside one full day for
  sympathetic_special and currency_analysis (they share equipment)
- traced_* categories need a dedicated session because the
  raking-light setup is fiddly
- **Output:** ~3,000 more training samples

### Final push — train each model

- Train each of the 16 models on Google Colab (free GPU). Each takes
  4–8 hours of unattended compute.
- 16 categories × 6 hours average = ~4 days of GPU time, but they
  can run in parallel across multiple Colab sessions / accounts.

---

# When you should scope down

If your defense is in 3 weeks, not 4+, ship 8–10 categories instead of
16. The capstone story is "we shipped a forensic detection system with
N working categories and a clear path for the rest." That's stronger
than "we shipped 16 mediocre models."

**Recommended scope-down to 8 (the highest-impact subset):**

1. digital_cut_paste (already done)
2. digital_desktop
3. addition_insertion
4. addition_interlineation
5. obliteration_whiteout
6. obliteration_ink
7. erasure_mechanical
8. currency_analysis

These cover the most common real-world forgeries Filipino users will
encounter and skip the most equipment-heavy ones. The remaining 8 can
be marked as "future work" in the defense slides.

---

# Where to find sample images / inspiration

- **Roboflow Universe** — https://universe.roboflow.com/ — search
  category names like "signature forgery", "forged document",
  "document tampering". Quality varies; treat as supplementary.
- **Hugging Face datasets** — search "document" — modern
  Parquet-format datasets that work with `fetch_sources.py`.
  CORD-v2 (receipts) and FUNSD (forms) are confirmed working.
- **Bangko Sentral ng Pilipinas** — https://www.bsp.gov.ph — official
  Philippine peso security feature documentation.
- **Forensic-document-examination textbooks** — Hilton's "Scientific
  Examination of Questioned Documents" and Osborn's "Questioned
  Documents" both have visual references for every category here.
  Use the photos as visual *guidance* (don't include them in the
  dataset — copyright).
- **Wikipedia Commons** — UV-fluorescence images of various
  currencies, signature forgery examples, public-domain document
  scans.
- **Government form templates** — DepEd, BIR, SSS, DFA all publish
  blank PDF forms. Render to JPG → instant negatives + bases for
  your fake-document creation in `digital_desktop`.

---

# Final notes

**Most important advice:** the per-category counts above are the
"recommended" tier. If you only do half of each number, your models
will still be functional. **The thing you cannot half-do is the
negatives.** A model with 50 forgeries and 100 negatives generalizes
better than a model with 200 forgeries and 0 negatives. Negative
samples are how you tell the model what is *not* a forgery, and that
is the foundation of "no hallucinations."

**Second most important advice:** photograph each forgery from at
least 3 angles and 2 lighting conditions. Real users uploading to
Revelator will not photograph documents under perfect studio light.
Variance in capture conditions is more valuable than variance in
forgery type.

**Honest expectation:** even with the recommended dataset numbers,
expect mAP@50 in the 0.70–0.85 range across categories. Forensic
detection at >0.90 mAP on real-world inputs is research-level. Your
defense should position Revelator as a **screening tool that
complements human examination**, not a replacement. The About page
already does this — keep that framing.
