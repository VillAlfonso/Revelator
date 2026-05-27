import React, { useState } from 'react';
import {
  Fingerprint, FileEdit, Layers, EyeOff, FlaskConical, Banknote,
  ChevronDown, ChevronRight, Image as ImageIcon, CornerDownRight,
} from 'lucide-react';
import { useTheme } from '../App';
import { themed, tintedBg } from '../themeColors';

const GROUPS = [
  {
    id: 'traced',
    label: 'Traced Signatures',
    Icon: Fingerprint,
    color: '#c4b5fd',
    description: 'A genuine signature is physically reproduced using an intermediary guide, carbon paper, light table, or projector. The forger follows a real signature rather than inventing one, producing subtle artifacts from the tracing method.',
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
        description: 'A light table or projector throws the genuine signature as a shadow onto paper. The forger traces the projected lines with pen. No grooves or carbon residue, only the telltale monotony of following a projected guide.',
        indicators: ['Uniform / monotonous pen pressure', 'Micro-tremors throughout', 'Frequent pen lifts', 'No carbon residue, no grooves', 'Suspiciously perfect match to original'],
      },
    ],
  },
  {
    id: 'alteration',
    label: 'Document Alteration',
    Icon: FileEdit,
    color: '#fbbf24',
    description: 'An authentic document is modified after the fact, text is added between lines or inside words, or existing content is erased (chemically or mechanically) and replaced. The original paper and its surrounding content remain genuine.',
    categories: [
      {
        id: 'addition_insertion',
        label: 'Addition, Insertion',
        description: 'Characters or digits are added inside a word or number to change its meaning (e.g., "1000" → "10000"). New strokes appear between or alongside existing ones, often with visible crowding, ink mismatches, or morphological inconsistency.',
        indicators: ['Crowding or tight spacing', 'Ink density mismatch', 'Stroke rhythm inconsistency', 'Baseline misalignment', 'Logical value conflict'],
      },
      {
        id: 'addition_interlineation',
        label: 'Addition, Interlineation',
        description: 'New text is squeezed into the whitespace between existing printed lines, not inside a word. The inserted writing often uses a smaller size or different pen to fit the narrow gap.',
        indicators: ['Smaller text size than surrounding', 'Different pen baseline', 'Different ink color or texture'],
      },
      {
        id: 'erasure_chemical',
        label: 'Erasure, Chemical',
        description: 'Original ink is dissolved with a solvent (bleach, acetone, commercial eradicator). The cleaned area is then written on or printed over. Solvents leave characteristic tide marks, ghosting, and paper fiber damage.',
        indicators: ['Halo / tide mark around altered zone', 'Ink ghosting of original text', 'Paper fiber damage', 'New text on visibly damaged background', 'Sheen difference under oblique light'],
      },
      {
        id: 'erasure_mechanical',
        label: 'Erasure, Mechanical',
        description: 'Original ink is scraped away with a razor blade, sandpaper, or eraser. The abraded area is then written or printed over. Abrasion leaves a rough "fuzzy patch" of disturbed paper fibers.',
        indicators: ["Abraded fibers ('fuzzy patch')", 'Shadow patch or sheen', 'Ghost ink particles', 'Paper thinning', 'Jagged void boundary', 'Ink feathering into damaged area'],
      },
    ],
  },
  {
    id: 'digital',
    label: 'Digital Fabrication',
    Icon: Layers,
    color: '#38bdf8',
    description: 'Software is used to create or manipulate document content. A document may be fabricated entirely from scratch, or genuine elements (signatures, stamps) may be digitally transplanted onto another document.',
    categories: [
      {
        id: 'digital_cut_paste',
        label: 'Digital, Cut & Paste',
        description: 'A genuine element (signature, seal, or stamp) is digitally extracted from one image and composited onto a different document. The transplanted element often carries halos, pixelation, DPI mismatches, or inconsistent shadows.',
        indicators: ['Halo or fringe around element', 'Pixelation or aliasing at edges', 'Background inconsistency under element', 'Compression artefacts', 'DPI or resolution mismatch', 'Inconsistent shadow or lighting'],
      },
      {
        id: 'digital_desktop',
        label: 'Digital, Desktop',
        description: 'The entire document is fabricated from scratch in software (Word, Canva, Photoshop, etc.). No physical paper ever existed. Indicators include unnaturally perfect typography, template-like layout, and a complete absence of physical paper realism.',
        indicators: ['Perfect digital typography throughout', 'Font consistency across entire doc', 'Forms or template layout', 'Signature quality mismatch vs printed text', 'Zero physical paper realism (no grain, no tilt)'],
      },
      {
        id: 'digital_scanned',
        label: 'Digital, Scanned',
        description: 'A real document is scanned, then digital elements (dates, signatures, stamps) are composited onto the scan image. The scan provides a realistic paper background while inserted elements betray themselves through scan-noise inconsistencies.',
        indicators: ['Scan noise inconsistency around inserted element', 'Stamp or signature flatness vs paper grain', 'Global tilt vs local perfect alignment', 'Compression level mismatch', 'Resolution halo around element', 'Font or field inconsistency'],
      },
    ],
  },
  {
    id: 'obliteration',
    label: 'Obliteration',
    Icon: EyeOff,
    color: '#f87171',
    description: 'Original content is intentionally concealed, not erased or replaced, but covered. Ink, correction fluid, or opaque pigment is applied over existing text to hide it while the surrounding document remains intact.',
    categories: [
      {
        id: 'obliteration_ink',
        label: 'Obliteration, Ink',
        description: 'Original text is scribbled over with a pen or marker, rendering it visually illegible. The underlying text may still be recoverable by infrared photography or other forensic techniques.',
        indicators: ['Ink scribbled over existing text', 'Possible underlying text visible via IR'],
      },
      {
        id: 'obliteration_whiteout',
        label: 'Obliteration, White Out',
        description: 'Correction fluid (Wite-Out, Tipp-Ex) is applied as an opaque white layer over existing text. The fluid leaves a distinctive raised, chalky surface texture that is visible to touch and sometimes to oblique light.',
        indicators: ['Correction fluid layer over text', 'Raised chalky surface texture', 'Whitened patch inconsistent with paper'],
      },
      {
        id: 'obliteration_pigment',
        label: 'Obliteration, Pigment',
        description: 'An opaque marker, paint, or solid pigment is used to cover text. Unlike whiteout, pigment obliteration may use any color and can be detected by the coating\'s opacity and edge characteristics.',
        indicators: ['Opaque marker or paint over text', 'Coating edge visible under magnification'],
      },
    ],
  },
  {
    id: 'sympathetic',
    label: 'Sympathetic Ink',
    Icon: FlaskConical,
    color: '#34d399',
    description: 'Writing that is invisible under normal conditions, either because no ink was deposited (pure pressure indentation) or because the ink only becomes visible under a specific stimulus such as heat, UV light, or a chemical reagent.',
    categories: [
      {
        id: 'sympathetic_indented',
        label: 'Sympathetic, Indented Writing',
        description: 'Writing pressure alone, with no ink, creates grooves on paper beneath the written-on sheet. The indented text contains no ink and is only visible by raking light or an electrostatic detection device (ESDA). Often used to reveal secondary documents.',
        indicators: ['Pressure indentations present on paper', 'No visible ink in grooves', 'Revealed by raking or oblique light', 'ESDA / electrostatic detection'],
      },
      {
        id: 'sympathetic_special',
        label: 'Sympathetic, Special Ink',
        description: 'An invisible or near-invisible substance is used to write, then later revealed by an external stimulus. Classic examples include heat-activated (lemon juice, milk), UV-fluorescent inks, and chemical reagent-activated compounds.',
        indicators: ['Heat-activated: text browns or chars', 'Chemical-activated: color reaction appears', 'UV / fluorescent glow under blacklight', 'Specific substances (lemon, milk, phenolphthalein)'],
      },
    ],
  },
  {
    id: 'currency',
    label: 'Currency Counterfeit',
    Icon: Banknote,
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

function ImageStub() {
  return (
    <div style={{
      border: '1px dashed #1d3825',
      borderRadius: 6,
      background: '#020b05',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: 140,
      gap: 8,
      padding: 12,
    }}>
      <ImageIcon size={32} strokeWidth={1.4} style={{ opacity: 0.25, color: '#00ff66' }} />
      <div className="mono" style={{ fontSize: 10, letterSpacing: 2, color: '#2a4d32', textTransform: 'uppercase', textAlign: 'center' }}>
        Example Image
      </div>
      <div className="mono" style={{ fontSize: 9, color: '#1d3825', textAlign: 'center', letterSpacing: 1 }}>
        Coming Soon
      </div>
    </div>
  );
}

function CategoryCard({ cat, groupColor }) {
  const { theme } = useTheme();
  const [open, setOpen] = useState(false);
  const accent = themed(groupColor, theme);

  return (
    <div style={{
      background: theme === 'light' ? '#ffffff' : '#030e07',
      border: `1px solid ${open ? tintedBg(groupColor, theme, 0.35) : (theme === 'light' ? '#d0dcd4' : '#112418')}`,
      borderRadius: 6,
      overflow: 'hidden',
      transition: 'border-color 0.15s, box-shadow 0.15s',
      boxShadow: open ? `0 2px 12px ${tintedBg(groupColor, theme, 0.1)}` : 'none',
    }}>
      <button
        onClick={() => setOpen(s => !s)}
        style={{
          width: '100%', background: 'transparent', border: 'none', cursor: 'pointer',
          padding: '14px 16px', textAlign: 'left',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1, minWidth: 0 }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%', background: accent, flexShrink: 0,
            boxShadow: theme === 'dark' ? `0 0 8px ${accent}aa` : 'none',
          }} />
          <span className="oswald" style={{
            fontSize: 15, color: theme === 'light' ? '#0a1c11' : '#d8ffe6',
            letterSpacing: 1.5, textTransform: 'uppercase', fontWeight: 600,
          }}>
            {cat.label}
          </span>
        </div>
        {open
          ? <ChevronDown size={18} strokeWidth={2} style={{ color: theme === 'light' ? '#3a5040' : '#3f6e4a', flexShrink: 0 }} />
          : <ChevronRight size={18} strokeWidth={2} style={{ color: theme === 'light' ? '#3a5040' : '#3f6e4a', flexShrink: 0 }} />}
      </button>

      {open && (
        <div style={{ padding: '0 16px 18px' }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(140px, 200px) 1fr',
            gap: 18,
            alignItems: 'start',
          }}>
            <ImageStub />
            <div>
              <p style={{
                color: theme === 'light' ? '#1a3024' : '#cfe9d8',
                fontSize: 14, lineHeight: 1.75, margin: '0 0 14px',
              }}>
                {cat.description}
              </p>
              <div className="mono" style={{
                fontSize: 10, letterSpacing: 2,
                color: theme === 'light' ? '#3a5040' : '#3f6e4a',
                textTransform: 'uppercase', marginBottom: 8, fontWeight: 600,
              }}>
                Key Indicators
              </div>
              <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
                {cat.indicators.map((ind, i) => (
                  <li key={i} style={{
                    color: theme === 'light' ? '#0a1c11' : '#86efac',
                    fontSize: 13, lineHeight: 1.7, paddingLeft: 0, marginBottom: 4,
                    display: 'flex', alignItems: 'flex-start', gap: 8,
                  }}>
                    <CornerDownRight size={14} strokeWidth={2.2} style={{ color: accent, flexShrink: 0, marginTop: 3 }} />
                    <span>{ind}</span>
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
  const { theme } = useTheme();
  const [collapsed, setCollapsed] = useState(false);
  const accent = themed(group.color, theme);
  const Icon = group.Icon;

  return (
    <section style={{ marginBottom: 36 }}>
      <button
        onClick={() => setCollapsed(s => !s)}
        style={{
          width: '100%', background: 'transparent', border: 'none', cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: 14, padding: '0 0 16px',
          borderBottom: `1px solid ${tintedBg(group.color, theme, 0.25)}`,
          marginBottom: 16,
        }}
      >
        <div style={{
          width: 40, height: 40, borderRadius: 8,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: tintedBg(group.color, theme, 0.12),
          border: `1px solid ${tintedBg(group.color, theme, 0.3)}`,
          flexShrink: 0,
          boxShadow: theme === 'dark' ? `0 0 12px ${tintedBg(group.color, theme, 0.25)}` : 'none',
        }}>
          <Icon size={20} strokeWidth={2} style={{ color: accent }} />
        </div>
        <div style={{ flex: 1, textAlign: 'left' }}>
          <div className="oswald" style={{
            fontSize: 18, color: accent, letterSpacing: 2,
            textTransform: 'uppercase', fontWeight: 700,
          }}>
            {group.label}
          </div>
          <div className="mono" style={{
            fontSize: 11, color: theme === 'light' ? '#3a5040' : '#3f6e4a',
            letterSpacing: 1.5, marginTop: 3,
          }}>
            {group.categories.length} {group.categories.length === 1 ? 'type' : 'types'}
          </div>
        </div>
        {collapsed
          ? <ChevronRight size={20} strokeWidth={2} style={{ color: theme === 'light' ? '#3a5040' : '#3f6e4a' }} />
          : <ChevronDown size={20} strokeWidth={2} style={{ color: theme === 'light' ? '#3a5040' : '#3f6e4a' }} />}
      </button>

      {!collapsed && (
        <>
          <p style={{
            color: theme === 'light' ? '#1a3024' : '#cfe9d8',
            fontSize: 14, lineHeight: 1.75, margin: '0 0 16px',
          }}>
            {group.description}
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
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
  const { theme } = useTheme();

  return (
    <div style={{ maxWidth: 820, margin: '0 auto' }}>
      <div style={{ marginBottom: 32 }}>
        <div className="mono" style={{
          fontSize: 10, letterSpacing: 3,
          color: theme === 'light' ? '#3a5040' : '#3f6e4a',
          textTransform: 'uppercase', marginBottom: 10,
          display: 'inline-flex', alignItems: 'center', gap: 8,
        }}>
          <Fingerprint size={14} strokeWidth={2} />
          Forensics Guide
        </div>
        <h1 className="oswald" style={{
          fontSize: 30, color: theme === 'light' ? '#003d17' : '#00ff66',
          letterSpacing: 3, textTransform: 'uppercase', margin: 0, fontWeight: 700,
          textShadow: theme === 'dark' ? '0 0 20px rgba(0,255,102,0.3)' : 'none',
        }}>
          Document Forgery Types
        </h1>
        <p style={{
          color: theme === 'light' ? '#1a3024' : '#cfe9d8',
          fontSize: 15, lineHeight: 1.75, margin: '12px 0 0',
        }}>
          Revelator detects 16 categories of document forgery across 6 groups. Each category uses a tailored
          analysis pipeline tuned to its specific physical or digital indicators. Click any category to expand
          its description, indicators, and example image.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 32 }}>
        {GROUPS.map(g => {
          const accent = themed(g.color, theme);
          const Icon = g.Icon;
          return (
            <div key={g.id} style={{
              display: 'flex', alignItems: 'center', gap: 8,
              background: tintedBg(g.color, theme, 0.08),
              border: `1px solid ${tintedBg(g.color, theme, 0.3)}`,
              borderRadius: 6, padding: '6px 12px',
            }}>
              <Icon size={14} strokeWidth={2.2} style={{ color: accent }} />
              <span className="mono" style={{
                fontSize: 11, color: accent, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600,
              }}>
                {g.label}
              </span>
              <span className="mono" style={{
                fontSize: 10, color: theme === 'light' ? '#3a5040' : '#3f6e4a',
              }}>
                ×{g.categories.length}
              </span>
            </div>
          );
        })}
      </div>

      {GROUPS.map(group => (
        <GroupSection key={group.id} group={group} />
      ))}

      <div className="card" style={{
        marginTop: 8, padding: '14px 18px',
        borderLeft: `3px solid ${theme === 'light' ? '#6da884' : '#1d3825'}`,
      }}>
        <p className="mono" style={{
          fontSize: 11, color: theme === 'light' ? '#3a5040' : '#5a7a64',
          margin: 0, lineHeight: 1.75, letterSpacing: 0.5,
        }}>
          Analysis is powered by Gemini Vision with a custom forensic prompt chain. Results are probabilistic -
          physical examination by a qualified document examiner is required for legal or evidentiary use.
        </p>
      </div>
    </div>
  );
}
