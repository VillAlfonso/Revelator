// Master catalog of all 16 forgery categories, used by Scan and SampleGallery.
// `apiKey` matches the leaf class id the backend's /analyze endpoint accepts.
// `id`     is the URL slug used by /samples/:categoryId.
// `tier`   1 = easy, 2 = medium, 3 = hard (informs grouping + accent color).
// Colors stay inside a green/cyan/lime spectrum to keep the matrix theme coherent.

export const TIER_COLORS = {
  1: '#00ff66', // neon green
  2: '#00ffaa', // cyan-green
  3: '#a3e635', // lime / chartreuse
};

export const TIER_META = {
  1: { label: 'Tier 1 · Surface',   sublabel: 'Digital and surface-level alterations — phone-friendly capture' },
  2: { label: 'Tier 2 · Substrate', sublabel: 'Paper-and-ink alterations — close-range or oblique-light capture' },
  3: { label: 'Tier 3 · Spectral',  sublabel: 'Specialized optics — UV, raking light, security features' },
};

export const CATEGORIES = [
  // ── Tier 1 — Surface / digital ────────────────────────────────────────
  {
    id: 'cut_paste',         apiKey: 'digital_cut_paste',       tier: 1,
    code: 'CUT', icon: '✂',   color: '#00ff66',
    title: 'Cut and Paste',
    description: 'Image regions spliced from one document into another to fabricate content.',
  },
  {
    id: 'desktop',           apiKey: 'digital_desktop',         tier: 1,
    code: 'DTP', icon: '⌨',   color: '#3df58a',
    title: 'Desktop Publishing',
    description: 'Whole-document fabrication built in Word, Canva, or Photoshop.',
  },
  {
    id: 'insertion',         apiKey: 'addition_insertion',      tier: 1,
    code: 'INS', icon: '+',   color: '#56ff8a',
    title: 'Insertion',
    description: 'New characters or digits added inside existing text to change its meaning.',
  },
  {
    id: 'interlineation',    apiKey: 'addition_interlineation', tier: 1,
    code: 'ITL', icon: '≡',   color: '#7cffaf',
    title: 'Interlineation',
    description: 'Extra writing squeezed between existing lines of a document.',
  },
  {
    id: 'whiteout',          apiKey: 'obliteration_whiteout',   tier: 1,
    code: 'WHT', icon: '◻',   color: '#9bffba',
    title: 'White Out',
    description: 'Correction fluid covering original text, with new content written on top.',
  },

  // ── Tier 2 — Physical substrate ───────────────────────────────────────
  {
    id: 'ink_obliteration',  apiKey: 'obliteration_ink',        tier: 2,
    code: 'INK', icon: '▮',   color: '#00ffaa',
    title: 'Ink Obliteration',
    description: 'Original text scribbled or crossed out with ink to conceal it.',
  },
  {
    id: 'pigment',           apiKey: 'obliteration_pigment',    tier: 2,
    code: 'PIG', icon: '⬛',   color: '#3affb9',
    title: 'Opaque Pigment',
    description: 'Paint or thick marker fully blocking underlying text.',
  },
  {
    id: 'mech_erasure',      apiKey: 'erasure_mechanical',      tier: 2,
    code: 'MEC', icon: '⌫',   color: '#5fffc4',
    title: 'Mechanical Erasure',
    description: 'Text physically removed by eraser, blade, sandpaper, or scraping.',
  },
  {
    id: 'chem_erasure',      apiKey: 'erasure_chemical',        tier: 2,
    code: 'CHM', icon: '⚗',   color: '#74ffd0',
    title: 'Chemical Erasure',
    description: 'Ink dissolved or lifted using solvents, ink-eraser pens, or bleach.',
  },
  {
    id: 'scanned',           apiKey: 'digital_scanned',         tier: 2,
    code: 'SCN', icon: '⎙',   color: '#9bffe0',
    title: 'Scanned Documents',
    description: 'Forgery printed and re-scanned to mask its digital origin.',
  },

  // ── Tier 3 — Spectral / specialized ───────────────────────────────────
  {
    id: 'carbon',            apiKey: 'traced_carbon',           tier: 3,
    code: 'CRB', icon: '◤',   color: '#a3e635',
    title: 'Carbon Transfer',
    description: 'Signature traced via carbon paper, then darkened with ink.',
  },
  {
    id: 'indentation',       apiKey: 'traced_indentation',      tier: 3,
    code: 'IDN', icon: '⌇',   color: '#b6ec57',
    title: 'Indentation Tracing',
    description: 'Pressure-impressed groove on a sheet, later traced with ink.',
  },
  {
    id: 'projection',        apiKey: 'traced_projection',       tier: 3,
    code: 'PRJ', icon: '⌖',   color: '#c5f071',
    title: 'Projection Tracing',
    description: 'Forger traces over a back-lit projection of an authentic document.',
  },
  {
    id: 'sym_indented',      apiKey: 'sympathetic_indented',    tier: 3,
    code: 'SYI', icon: '〰',   color: '#d3f48a',
    title: 'Indented Writing',
    description: 'Recovery of pressure shadows left on the sheet beneath original writing.',
  },
  {
    id: 'sym_special',       apiKey: 'sympathetic_special',     tier: 3,
    code: 'UVI', icon: '☢',   color: '#e2f8a3',
    title: 'Special Ink (UV)',
    description: 'Writing that fluoresces only under UV — invisible in normal light.',
  },
  {
    id: 'currency',          apiKey: 'currency_analysis',       tier: 3,
    code: 'CUR', icon: '₱',   color: '#f0ffbe',
    title: 'Currency Analysis',
    description: 'Authenticity check on banknotes — watermarks, threads, UV features.',
  },
];

// Lookup helpers
export const CATEGORY_BY_ID  = Object.fromEntries(CATEGORIES.map(c => [c.id, c]));
export const CATEGORY_BY_KEY = Object.fromEntries(CATEGORIES.map(c => [c.apiKey, c]));

export function categoriesByTier(tier) {
  return CATEGORIES.filter(c => c.tier === tier);
}

// Per-category capture guidance shown on the SampleGallery page.
export const GUIDANCE = {
  cut_paste: {
    shooting: [
      'Lay the document flat under even light — no glare on the splice region',
      'Capture full-page so the model can see boundaries between pasted and original',
      'Avoid cropping mid-character — give 1cm margin around suspect regions',
    ],
    detector: 'Looks for inconsistent JPEG quantization, mismatched lighting, and seams where pixel statistics break.',
  },
  desktop: {
    shooting: [
      'Photograph or scan the printed copy at high resolution (≥300 DPI equivalent)',
      'Include security features (logos, seals, holograms) in frame',
      'Tilt slightly off-axis to surface print-from-screen pixel grids',
    ],
    detector: 'Looks for typeface drift, alignment slips, and missing or wrong-position security elements.',
  },
  insertion: {
    shooting: [
      'Get close enough that text is sharp at full resolution',
      'Capture the entire altered region plus surrounding context',
      'No flash — it can wash out ink-color drift the model relies on',
    ],
    detector: 'Looks for ink-shade differences, cramped spacing, and pen-pressure changes within a word or number.',
  },
  interlineation: {
    shooting: [
      'Frame the interlineation centered between two lines of original text',
      'Use diffuse light from above; avoid harsh side shadows',
      'For very tight gaps, take a second close-up to capture stroke detail',
    ],
    detector: 'Looks for cramped writing in line gaps, ink-shade mismatches, and slight tilt from a forced angle.',
  },
  whiteout: {
    shooting: [
      'Shoot under raking (low-angle) light to reveal the topology of the white-out patch',
      'Capture both the patch and 2cm of surrounding clean paper',
      'Take a normal-light shot too — texture differences show up across both',
    ],
    detector: 'Looks for matte sheen, raised topology, and irregular edges around the covered area.',
  },
  ink_obliteration: {
    shooting: [
      'Strong overhead light may surface ghost text bleeding through the ink',
      'Avoid auto-exposure — locking exposure preserves ink-density signal',
      'Capture multiple angles if the obliteration is glossy',
    ],
    detector: 'Looks for ink-density anomalies, residual character outlines, and uniform machine-like coverage.',
  },
  pigment: {
    shooting: [
      'Side lighting reveals brush strokes and applicator marks',
      'Photograph the entire opaque patch including sharp edges',
      'Don\'t over-correct exposure — let dark areas stay dark',
    ],
    detector: 'Looks for solid uniform fill, raised paint texture, and applicator-stroke patterns.',
  },
  mech_erasure: {
    shooting: [
      'Raking light is mandatory — it shows the disturbed paper fibers',
      'Capture against a black backdrop so light bounce stays controlled',
      'Take a transmission shot (light behind paper) if paper is thinned',
    ],
    detector: 'Looks for raised fibers, paper-thinning, ghost text, and slight discoloration where ink was lifted.',
  },
  chem_erasure: {
    shooting: [
      'Watch for brown / yellow halos — those are the chemical signature',
      'Shoot under both normal and UV light if available — chemistry often fluoresces',
      'Avoid white balance auto-correct; the cast carries information',
    ],
    detector: 'Looks for chemical halos, etched paper, residual ink ghosts, and UV-fluorescent residue.',
  },
  scanned: {
    shooting: [
      'For PDFs, export each page as a PNG and submit individually',
      'For prints, scan at the highest resolution your scanner supports',
      'Slightly tilt photographed prints to dodge moiré',
    ],
    detector: 'Looks for compounding compression artifacts, halftone patterns, and edge softness from re-capture.',
  },
  carbon: {
    shooting: [
      'Macro / close-up — character-level detail matters here',
      'Even diffuse light, no shadows in the stroke',
      'Submit the full signature plus 2cm context above and below',
    ],
    detector: 'Looks for unnaturally uniform stroke speed, faint carbon shadow alongside the ink, and broken character continuity.',
  },
  indentation: {
    shooting: [
      'A side lamp at 10–30° from horizontal is required — flash or top-down won\'t work',
      'Phone parallel to the page; canals show as shadow stripes',
      'Hold the camera steady — ideally a tripod or stable surface',
    ],
    detector: 'Looks for canal grooves, ink filling indentations precisely, and depression rings around the signature.',
  },
  projection: {
    shooting: [
      'Get the entire signature in frame plus surrounding text',
      'Even diffuse light — projection artifacts hide under harsh contrast',
      'High resolution helps detect ghosting at stroke edges',
    ],
    detector: 'Looks for slight scaling vs the genuine signature, edge ghosting, and unnaturally consistent stroke uniformity.',
  },
  sym_indented: {
    shooting: [
      'Required: low-angle light source (smartphone flashlight at the side works)',
      'Photograph the blank-looking sheet — that\'s where the impressions live',
      'Black backdrop helps suppress reflected light',
    ],
    detector: 'Looks for shadow patterns from pressure impressions on otherwise blank paper.',
  },
  sym_special: {
    shooting: [
      'A 365nm UV flashlight gives the strongest signal — capture under it',
      'Take a paired normal-light shot too; the model uses both',
      'Minimize ambient light leakage — work in a dim room',
    ],
    detector: 'Looks for UV fluorescence patterns, presence of writing invisible in normal light, and missing expected security ink.',
  },
  currency: {
    shooting: [
      'Both sides — submit two scans (front + back)',
      'Capture security thread, watermark, and microprinting in frame — don\'t crop edges',
      'Tilt slightly so optically-variable inks register correctly',
    ],
    detector: 'Looks for missing watermarks, off-color security threads, microprinting blur, and incorrect UV response.',
  },
};
