import React, { useState } from 'react';

const GROUPS = [
  {
    id: 'traced',
    label: 'Traced Signatures',
    icon: '◈',
    color: '#c4b5fd',
    description: 'A genuine signature is physically reproduced using an intermediary guide — carbon paper, light table, or projector. The forger follows a real signature rather than inventing one, producing subtle artifacts from the tracing method.',
    categories: [
      {
        id: 'traced_carbon',
        label: 'Carbon Tracing',
        description: 'Carbon paper placed beneath the genuine signature transfers a faint "blueprint" via pressure. The forger then inks over the faint transfer, leaving behind telltale carbon residue and hesitant strokes.',
        indicators: ['Faint carbon residue along strokes', 'Hesitation or tremor following blueprint', 'Uniform line weight', 'Misalignment from carbon transfer'],
      },
      {
        id: 'traced_indentation',
        label: 'Indentation Tracing',
        description: 'A pen pressed hard onto paper placed over a genuine signature creates physical grooves. The forger inks inside these canals, leaving a colorless depression (halo) around strokes visible under raking light.',
        indicators: ['Halo / colorless depression around strokes', 'Ink not filling indented path', 'Hesitation or tremor'],
      },
      {
        id: 'traced_projection',
        label: 'Projection Tracing',
        description: 'A light table or projector throws the genuine signature as a shadow onto paper. The forger traces the projected lines with pen. No grooves or carbon residue — only the telltale monotony of following a projected guide.',
        indicators: ['Uniform / monotonous pen pressure', 'Micro-tremors throughout', 'Frequent pen lifts', 'No carbon residue, no grooves', 'Suspiciously perfect match to original'],
      },
    ],
  },
  {
    id: 'alteration',
    label: 'Document Alteration',
    icon: '◆',
    color: '#fbbf24',
    description: 'An authentic document is modified after the fact — text is added between lines or inside words, or existing content is erased (chemically or mechanically) and replaced. The original paper and its surrounding content remain genuine.',
    categories: [
      {
        id: 'addition_insertion',
        label: 'Addition — Insertion',
        description: 'Characters or digits are added inside a word or number to change its meaning (e.g., "1000" → "10000"). New strokes appear between or alongside existing ones, often with visible crowding, ink mismatches, or morphological inconsistency.',
        indicators: ['Crowding or tight spacing', 'Ink density mismatch', 'Stroke rhythm inconsistency', 'Baseline misalignment', 'Logical value conflict'],
      },
      {
        id: 'addition_interlineation',
        label: 'Addition — Interlineation',
        description: 'New text is squeezed into the whitespace between existing printed lines, not inside a word. The inserted writing often uses a smaller size or different pen to fit the narrow gap.',
        indicators: ['Smaller text size than surrounding', 'Different pen baseline', 'Different ink color or texture'],
      },
      {
        id: 'erasure_chemical',
        label: 'Erasure — Chemical',
        description: 'Original ink is dissolved with a solvent (bleach, acetone, commercial eradicator). The cleaned area is then written on or printed over. Solvents leave characteristic tide marks, ghosting, and paper fiber damage.',
        indicators: ['Halo / tide mark around altered zone', 'Ink ghosting of original text', 'Paper fiber damage', 'New text on visibly damaged background', 'Sheen difference under oblique light'],
      },
      {
        id: 'erasure_mechanical',
        label: 'Erasure — Mechanical',
        description: 'Original ink is scraped away with a razor blade, sandpaper, or eraser. The abraded area is then written or printed over. Abrasion leaves a rough "fuzzy patch" of disturbed paper fibers.',
        indicators: ["Abraded fibers ('fuzzy patch')", 'Shadow patch or sheen', 'Ghost ink particles', 'Paper thinning', 'Jagged void boundary', 'Ink feathering into damaged area'],
      },
    ],
  },
  {
    id: 'digital',
    label: 'Digital Fabrication',
    icon: '▣',
    color: '#38bdf8',
    description: 'Software is used to create or manipulate document content. A document may be fabricated entirely from scratch, or genuine elements (signatures, stamps) may be digitally transplanted onto another document.',
    categories: [
      {
        id: 'digital_cut_paste',
        label: 'Digital — Cut & Paste',
        description: 'A genuine element (signature, seal, or stamp) is digitally extracted from one image and composited onto a different document. The transplanted element often carries halos, pixelation, DPI mismatches, or inconsistent shadows.',
        indicators: ['Halo or fringe around element', 'Pixelation or aliasing at edges', 'Background inconsistency under element', 'Compression artefacts', 'DPI or resolution mismatch', 'Inconsistent shadow or lighting'],
      },
      {
        id: 'digital_desktop',
        label: 'Digital — Desktop',
        description: 'The entire document is fabricated from scratch in software (Word, Canva, Photoshop, etc.). No physical paper ever existed. Indicators include unnaturally perfect typography, template-like layout, and a complete absence of physical paper realism.',
        indicators: ['Perfect digital typography throughout', 'Font consistency across entire doc', 'Forms or template layout', 'Signature quality mismatch vs printed text', 'Zero physical paper realism (no grain, no tilt)'],
      },
      {
        id: 'digital_scanned',
        label: 'Digital — Scanned',
        description: 'A real document is scanned, then digital elements (dates, signatures, stamps) are composited onto the scan image. The scan provides a realistic paper background while inserted elements betray themselves through scan-noise inconsistencies.',
        indicators: ['Scan noise inconsistency around inserted element', 'Stamp or signature flatness vs paper grain', 'Global tilt vs local perfect alignment', 'Compression level mismatch', 'Resolution halo around element', 'Font or field inconsistency'],
      },
    ],
  },
  {
    id: 'obliteration',
    label: 'Obliteration',
    icon: '▓',
    color: '#f87171',
    description: 'Original content is intentionally concealed — not erased or replaced, but covered. Ink, correction fluid, or opaque pigment is applied over existing text to hide it while the surrounding document remains intact.',
    categories: [
      {
        id: 'obliteration_ink',
        label: 'Obliteration — Ink',
        description: 'Original text is scribbled over with a pen or marker, rendering it visually illegible. The underlying text may still be recoverable by infrared photography or other forensic techniques.',
        indicators: ['Ink scribbled over existing text', 'Possible underlying text visible via IR'],
      },
      {
        id: 'obliteration_whiteout',
        label: 'Obliteration — White Out',
        description: 'Correction fluid (Wite-Out, Tipp-Ex) is applied as an opaque white layer over existing text. The fluid leaves a distinctive raised, chalky surface texture that is visible to touch and sometimes to oblique light.',
        indicators: ['Correction fluid layer over text', 'Raised chalky surface texture', 'Whitened patch inconsistent with paper'],
      },
      {
        id: 'obliteration_pigment',
        label: 'Obliteration — Pigment',
        description: 'An opaque marker, paint, or solid pigment is used to cover text. Unlike whiteout, pigment obliteration may use any color and can be detected by the coating\'s opacity and edge characteristics.',
        indicators: ['Opaque marker or paint over text', 'Coating edge visible under magnification'],
      },
    ],
  },
  {
    id: 'sympathetic',
    label: 'Sympathetic Ink',
    icon: '◌',
    color: '#34d399',
    description: 'Writing that is invisible under normal conditions — either because no ink was deposited (pure pressure indentation) or because the ink only becomes visible under a specific stimulus such as heat, UV light, or a chemical reagent.',
    categories: [
      {
        id: 'sympathetic_indented',
        label: 'Sympathetic — Indented Writing',
        description: 'Writing pressure alone, with no ink, creates grooves on paper beneath the written-on sheet. The indented text contains no ink and is only visible by raking light or an electrostatic detection device (ESDA). Often used to reveal secondary documents.',
        indicators: ['Pressure indentations present on paper', 'No visible ink in grooves', 'Revealed by raking or oblique light', 'ESDA / electrostatic detection'],
      },
      {
        id: 'sympathetic_special',
        label: 'Sympathetic — Special Ink',
        description: 'An invisible or near-invisible substance is used to write, then later revealed by an external stimulus. Classic examples include heat-activated (lemon juice, milk), UV-fluorescent inks, and chemical reagent-activated compounds.',
        indicators: ['Heat-activated: text browns or chars', 'Chemical-activated: color reaction appears', 'UV / fluorescent glow under blacklight', 'Specific substances (lemon, milk, phenolphthalein)'],
      },
    ],
  },
  {
    id: 'currency',
    label: 'Currency Counterfeit',
    icon: '◇',
    color: '#fbbf24',
    description: 'Suspected counterfeit banknotes or currency documents. The system evaluates security features, print quality, substrate characteristics, and known anti-counterfeiting elements for the suspected denomination.',
    categories: [
      {
        id: 'currency_analysis',
        label: 'Currency Analysis',
        description: 'Analysis of a suspected counterfeit banknote. The system checks print precision, microprinting legibility, security thread presence, color-shifting ink, watermark clarity, and paper substrate texture against known genuine specimen characteristics.',
        indicators: ['Counterfeit banknote suspected', 'Security feature integrity', 'Print quality evaluation', 'Substrate texture assessment'],
      },
    ],
  },
];

function ImageStub({ label }) {
  return (
    <div style={{
      border: '1px dashed #1d3825',
      borderRadius: 3,
      background: '#020b05',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: 140,
      gap: 8,
      padding: 12,
    }}>
      <div style={{ fontSize: 28, opacity: 0.18, color: '#00ff66' }}>▣</div>
      <div className="mono" style={{ fontSize: 9, letterSpacing: 2, color: '#2a4d32', textTransform: 'uppercase', textAlign: 'center' }}>
        Example Image
      </div>
      <div className="mono" style={{ fontSize: 8, color: '#1d3825', textAlign: 'center', letterSpacing: 1 }}>
        Coming Soon
      </div>
    </div>
  );
}

function CategoryCard({ cat, groupColor }) {
  const [open, setOpen] = useState(false);

  return (
    <div style={{
      background: '#030e07',
      border: `1px solid ${open ? groupColor + '33' : '#112418'}`,
      borderRadius: 3,
      overflow: 'hidden',
      transition: 'border-color 0.15s',
    }}>
      <button
        onClick={() => setOpen(s => !s)}
        style={{
          width: '100%', background: 'transparent', border: 'none', cursor: 'pointer',
          padding: '14px 16px', textAlign: 'left',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 0 }}>
          <div style={{
            width: 6, height: 6, borderRadius: '50%', background: groupColor, flexShrink: 0,
          }} />
          <span className="oswald" style={{
            fontSize: 14, color: '#d8ffe6', letterSpacing: 1.5, textTransform: 'uppercase',
          }}>
            {cat.label}
          </span>
        </div>
        <span className="mono" style={{ fontSize: 11, color: '#3f6e4a', flexShrink: 0 }}>
          {open ? '▲' : '▼'}
        </span>
      </button>

      {open && (
        <div style={{ padding: '0 16px 16px' }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(120px, 180px) 1fr',
            gap: 16,
            alignItems: 'start',
          }}>
            <ImageStub label={cat.label} />
            <div>
              <p style={{
                color: '#86efac', fontSize: 12, lineHeight: 1.7, margin: '0 0 12px',
              }}>
                {cat.description}
              </p>
              <div className="mono" style={{
                fontSize: 9, letterSpacing: 2, color: '#3f6e4a', textTransform: 'uppercase', marginBottom: 6,
              }}>
                Key Indicators
              </div>
              <ul style={{ margin: 0, paddingLeft: 16, listStyle: 'none' }}>
                {cat.indicators.map((ind, i) => (
                  <li key={i} style={{
                    color: '#6dba85', fontSize: 11, lineHeight: 1.7, paddingLeft: 0,
                    display: 'flex', alignItems: 'flex-start', gap: 6,
                  }}>
                    <span style={{ color: groupColor, flexShrink: 0, marginTop: 2, fontSize: 8 }}>▸</span>
                    {ind}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function GroupSection({ group }) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <section style={{ marginBottom: 32 }}>
      <button
        onClick={() => setCollapsed(s => !s)}
        style={{
          width: '100%', background: 'transparent', border: 'none', cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: 12, padding: '0 0 14px',
          borderBottom: `1px solid ${group.color}22`,
          marginBottom: 14,
        }}
      >
        <span style={{ fontSize: 18, color: group.color }}>{group.icon}</span>
        <div style={{ flex: 1, textAlign: 'left' }}>
          <div className="oswald" style={{
            fontSize: 16, color: group.color, letterSpacing: 2, textTransform: 'uppercase',
          }}>
            {group.label}
          </div>
          <div className="mono" style={{ fontSize: 9, color: '#3f6e4a', letterSpacing: 1.5, marginTop: 2 }}>
            {group.categories.length} {group.categories.length === 1 ? 'type' : 'types'}
          </div>
        </div>
        <span className="mono" style={{ fontSize: 11, color: '#3f6e4a' }}>
          {collapsed ? '▶' : '▼'}
        </span>
      </button>

      {!collapsed && (
        <>
          <p style={{ color: '#6dba85', fontSize: 12, lineHeight: 1.7, margin: '0 0 14px' }}>
            {group.description}
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {group.categories.map(cat => (
              <CategoryCard key={cat.id} cat={cat} groupColor={group.color} />
            ))}
          </div>
        </>
      )}
    </section>
  );
}

export default function ForensicsGuide() {
  return (
    <div style={{ maxWidth: 760, margin: '0 auto' }}>
      <div style={{ marginBottom: 28 }}>
        <div className="mono" style={{
          fontSize: 9, letterSpacing: 3, color: '#3f6e4a', textTransform: 'uppercase', marginBottom: 8,
        }}>
          ▣ Forensics Guide
        </div>
        <h1 className="oswald" style={{
          fontSize: 26, color: '#00ff66', letterSpacing: 3, textTransform: 'uppercase', margin: 0,
          textShadow: '0 0 20px rgba(0,255,102,0.3)',
        }}>
          Document Forgery Types
        </h1>
        <p style={{ color: '#6dba85', fontSize: 13, lineHeight: 1.7, margin: '10px 0 0' }}>
          Revelator detects 16 categories of document forgery across 6 groups. Each category uses a tailored
          analysis pipeline tuned to its specific physical or digital indicators. Click any category to expand
          its description, indicators, and example image.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 28 }}>
        {GROUPS.map(g => (
          <div key={g.id} style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: '#030e07', border: `1px solid ${g.color}33`,
            borderRadius: 2, padding: '5px 10px',
          }}>
            <span style={{ fontSize: 12, color: g.color }}>{g.icon}</span>
            <span className="mono" style={{ fontSize: 10, color: g.color, letterSpacing: 1, textTransform: 'uppercase' }}>
              {g.label}
            </span>
            <span className="mono" style={{ fontSize: 9, color: '#3f6e4a' }}>
              ×{g.categories.length}
            </span>
          </div>
        ))}
      </div>

      {GROUPS.map(group => (
        <GroupSection key={group.id} group={group} />
      ))}

      <div className="card" style={{ marginTop: 8, padding: '12px 16px', borderLeft: '3px solid #1d3825' }}>
        <p className="mono" style={{ fontSize: 10, color: '#3f6e4a', margin: 0, lineHeight: 1.7, letterSpacing: 0.5 }}>
          Analysis is powered by Gemini Vision with a custom forensic prompt chain. Results are probabilistic —
          physical examination by a qualified document examiner is required for legal or evidentiary use.
        </p>
      </div>
    </div>
  );
}
