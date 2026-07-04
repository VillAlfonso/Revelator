"""
Prompt analytics route, kept in its own file so it can be shared between
teammates working on the Gemini prompt independently of the rest of the app.

The plan: two collaborators tune the forensic prompt in parallel and only
need to swap two files to sync, this one and ``forgery/gemini_vision.py``.
Everything else in the codebase, auth, history, classrooms, payments,
remains untouched by that work.

Endpoint:
    GET /api/prompt-analysis  -> JSON consumed by the admin PromptDashboard
"""

import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["prompt-analytics"])

# Written by backend/evaluate_specimens.py after each specimen evaluation run.
ACCURACY_FILE = Path(__file__).resolve().parent.parent / "data" / "specimen_accuracy.json"


def extract_rules_from_prompt():
    """Read critical rules from gemini_vision.py at runtime."""
    try:
        gemini_path = Path(__file__).parent.parent / "forgery" / "gemini_vision.py"
        lines = gemini_path.read_text(encoding="utf-8").split("\n")

        rules = []

        # Collect the multi-line CRITICAL BRANCHING RULE block
        critical_lines = []
        in_critical = False
        for line in lines:
            if "CRITICAL BRANCHING RULE" in line and line.strip().startswith("CRITICAL"):
                in_critical = True
            if in_critical:
                s = line.strip()
                if s:
                    critical_lines.append(s)
                if s.startswith("NO") and "digital" in s:
                    break
        if critical_lines:
            rules.append({
                "title": "CRITICAL BRANCHING RULE - FIRST DECISION:",
                "text": " ".join(critical_lines),
            })

        # Collect single-line warning rule lines
        target_rules = ["BANK CHECK RULE", "INK LAYERING RULE", "INCOMPLETE WORD RULE",
                        "SEMANTIC CONFLICT / CHEMICAL ERASURE RULE", "GHOST TEXT vs. SYMPATHETIC INK RULE"]
        for line in lines:
            s = line.strip().lstrip("⚠️").strip()
            for rule_name in target_rules:
                if s.startswith(rule_name + ":"):
                    body = s[len(rule_name) + 1:].strip()
                    rules.append({"title": rule_name + ":", "text": body})
                    break

        return rules
    except Exception:
        return []


@router.get("/prompt-analysis/accuracy")
def get_system_accuracy():
    """Live specimen-evaluation accuracy, written by backend/evaluate_specimens.py.

    Returns {"status": "no_data"} until the harness has been run at least once.
    The frontend dashboards poll this endpoint so the numbers update on their own
    whenever a new evaluation run finishes.
    """
    if not ACCURACY_FILE.exists():
        return {
            "status": "no_data",
            "message": "No evaluation run yet. Run: cd backend && python evaluate_specimens.py --sample 3",
        }
    try:
        data = json.loads(ACCURACY_FILE.read_text(encoding="utf-8"))
        data["status"] = "ok"
        return data
    except Exception as exc:
        return {"status": "error", "message": f"Could not read accuracy file: {exc}"}


@router.get("/prompt-analysis")
def get_prompt_analysis():
    """Prompt analysis data, rules read live from gemini_vision.py."""
    rules = extract_rules_from_prompt()
    return {
        "system_prompt": {"total_words": 2847},
        "groups": {
            "traced": "#e74c3c",
            "alteration": "#f39c12",
            "digital": "#5b8def",
            "obliteration": "#9b59b6",
            "sympathetic": "#1abc9c",
            "currency": "#95a5a6",
        },
        "aux_prompts": [
            {"name": "SYSTEM_PROMPT", "word_count": 2847, "char_count": 18392, "purpose": "Main classification logic with category definitions, branching rules, and user-context injection."},
            {"name": "TRIAGE_PROMPT", "word_count": 420, "char_count": 2680, "purpose": "Fast screening: returns top 3 suspected categories without full reasoning."},
            {"name": "DISTINCTION_BLOCK (traced_projection vs digital)", "word_count": 150, "char_count": 950, "purpose": "Explicit rules to distinguish perfect-looking traced signatures from digital forgeries."},
        ],
        "rules": rules,
        "categories": [
            {"id": "traced_carbon", "label": "Traced - Carbon", "group": "traced", "word_count": 70, "detail_level": "MEDIUM", "first_line": "Carbon paper placed under genuine signature; forger traces with stylus, transfers carbon 'blueprint', then inks over.", "indicators": ["faint carbon residue along strokes","hesitation/tremor following blueprint","uniform line weight","misalignment from carbon transfer"], "distinctions": []},
            {"id": "traced_indentation", "label": "Traced - Indentation", "group": "traced", "word_count": 50, "detail_level": "MEDIUM", "first_line": "Pressure indentation/canal light effect - pen pressed into paper creates groove around strokes.", "indicators": ["halo/colorless depression around strokes","ink not filling indented path","hesitation or tremor"], "distinctions": []},
            {"id": "traced_projection", "label": "Traced - Projection", "group": "traced", "word_count": 300, "detail_level": "VERY HIGH", "first_line": "Light table or projector throws genuine signature onto paper; forger inks over projected lines.", "indicators": ["uniform/monotonous pen pressure","micro-tremors","frequent pen lifts","no carbon residue","no grooves","suspiciously perfect match"], "distinctions": [{"target": "digital_cut_paste", "reason": "Physical pen marks vs digital halo/pixelation"}, {"target": "digital_scanned", "reason": "Paper-fiber interaction vs flat-on-scan-grain"}]},
            {"id": "addition_insertion", "label": "Addition - Insertion", "group": "alteration", "word_count": 500, "detail_level": "VERY HIGH", "first_line": "Characters added inside a word/number to change meaning. Has TWO subtypes: A) digit in blank space, B) char converted by added stroke.", "indicators": ["crowding/tight spacing","ink density mismatch","stroke rhythm inconsistency","baseline misalignment","logical value conflict","ink texture mismatch (printed vs wet)","stroke layering / Z-axis","morphological inconsistency"], "distinctions": []},
            {"id": "addition_interlineation", "label": "Addition - Interlineation", "group": "alteration", "word_count": 30, "detail_level": "LOW", "first_line": "New writing squeezed BETWEEN existing lines (in whitespace, not inside a word).", "indicators": ["smaller text","different baseline","different ink"], "distinctions": []},
            {"id": "erasure_chemical", "label": "Erasure - Chemical", "group": "alteration", "word_count": 150, "detail_level": "HIGH", "first_line": "Original ink dissolved with solvent (bleach, acetone, eradicator), then new text written/printed in cleaned area.", "indicators": ["halo/tide mark","ink ghosting","paper fiber damage","new text on damaged background","oblique-light sheen difference"], "distinctions": []},
            {"id": "erasure_mechanical", "label": "Erasure - Mechanical", "group": "alteration", "word_count": 250, "detail_level": "HIGH", "first_line": "Original ink scraped off with razor/sandpaper/eraser, then replacement written/printed on scraped area.", "indicators": ["abraded fibers ('fuzzy patch')","shadow patch / sheen","ghost particles","paper thinning","jagged void boundary","ink feathering","logical word truncation"], "distinctions": []},
            {"id": "digital_cut_paste", "label": "Digital - Cut & Paste", "group": "digital", "word_count": 200, "detail_level": "HIGH", "first_line": "Genuine element (signature, stamp) digitally lifted and composited onto otherwise real document.", "indicators": ["halo/fringe","pixelation/aliasing","background inconsistency","compression artefacts","DPI mismatch","shadow/lighting","perfect leveling"], "distinctions": []},
            {"id": "digital_desktop", "label": "Digital - Desktop", "group": "digital", "word_count": 200, "detail_level": "HIGH", "first_line": "ENTIRE document fabricated from scratch in software (Word, Canva, Photoshop).", "indicators": ["perfect digital typography","font consistency across doc","forms & templates","signature-quality mismatch","zero physical realism"], "distinctions": []},
            {"id": "digital_scanned", "label": "Digital - Scanned", "group": "digital", "word_count": 200, "detail_level": "HIGH", "first_line": "Real document scanned, then digital elements composited onto scan image (stamp, signature, dates).", "indicators": ["scan-noise inconsistency","stamp/signature flatness","global tilt vs local alignment","compression-level mismatch","resolution halo","font/field inconsistency"], "distinctions": []},
            {"id": "obliteration_ink", "label": "Obliteration - Ink", "group": "obliteration", "word_count": 5, "detail_level": "VERY LOW", "first_line": "Original text scribbled out with ink.", "indicators": ["ink scribbled over original"], "distinctions": []},
            {"id": "obliteration_whiteout", "label": "Obliteration - White Out", "group": "obliteration", "word_count": 5, "detail_level": "VERY LOW", "first_line": "Correction fluid covering text.", "indicators": ["correction fluid covering text"], "distinctions": []},
            {"id": "sympathetic_indented", "label": "Sympathetic - Indented", "group": "sympathetic", "word_count": 15, "detail_level": "VERY LOW", "first_line": "Indented writing visible only via raking light. No ink in the grooves.", "indicators": ["pressure indentations on paper","no visible ink","raking light reveals"], "distinctions": []},
            {"id": "sympathetic_special", "label": "Sympathetic - Special Ink", "group": "sympathetic", "word_count": 200, "detail_level": "HIGH", "first_line": "Invisible ink revealed by external stimulus (heat, reagent, UV).", "indicators": ["heat-activated (browned/charred)","chemical-activated (color reaction)","UV/fluorescent","specific substances (lemon, milk, phenolphthalein)"], "distinctions": []},
            {"id": "currency_analysis", "label": "Currency", "group": "currency", "word_count": 5, "detail_level": "VERY LOW", "first_line": "Suspected counterfeit banknote.", "indicators": ["counterfeit banknote suspected"], "distinctions": []},
        ],
        "overlaps": [
            {"source": "traced_carbon", "target": "traced_indentation", "strength": 0.65, "severity": "MEDIUM", "from_prompt": True, "reason": "Both hand-drawn with hesitation/tremor. Carbon has residue; indentation has groove. Easy to confuse on low-res images."},
            {"source": "traced_carbon", "target": "traced_projection", "strength": 0.55, "severity": "MEDIUM", "from_prompt": True, "reason": "Both show uniform line weight from following a guide. Carbon = paper underneath; projection = light from above."},
            {"source": "traced_indentation", "target": "traced_projection", "strength": 0.55, "severity": "MEDIUM", "from_prompt": True, "reason": "Both hand-drawn from a visual reference. Indentation creates physical groove; projection does not."},
            {"source": "traced_projection", "target": "digital_cut_paste", "strength": 0.85, "severity": "HIGH", "from_prompt": True, "reason": "Both produce 'perfect-looking' signatures. Distinguish: physical pen marks vs digital halo/pixelation. Has explicit distinction block."},
            {"source": "traced_projection", "target": "digital_scanned", "strength": 0.85, "severity": "HIGH", "from_prompt": True, "reason": "Both look unnaturally clean. Distinguish: paper-fiber interaction vs flat-on-scan-grain. Has explicit distinction block."},
            {"source": "traced_indentation", "target": "digital_desktop", "strength": 0.75, "severity": "HIGH", "from_prompt": True, "reason": "OLD BIAS (now patched): the prompt used to say 'mechanical-looking text = traced'. Software-generated docs naturally look mechanical. Caused misclassification."},
            {"source": "traced_carbon", "target": "digital_cut_paste", "strength": 0.45, "severity": "LOW", "from_prompt": False, "reason": "Both can show ghost-like residue. Carbon = real ink residue; cut/paste = digital halo."},
            {"source": "sympathetic_indented", "target": "traced_indentation", "strength": 0.85, "severity": "HIGH", "from_prompt": False, "reason": "BOTH involve indentation/grooves. Difference: sympathetic_indented has grooves WITHOUT ink. traced_indentation has grooves WITH ink filling them. The prompt does NOT explicitly distinguish these, risk of confusion."},
            {"source": "digital_cut_paste", "target": "digital_desktop", "strength": 0.7, "severity": "MEDIUM", "from_prompt": True, "reason": "Both software-generated. Cut/paste = element on real doc; desktop = whole doc fabricated."},
            {"source": "digital_cut_paste", "target": "digital_scanned", "strength": 0.75, "severity": "HIGH", "from_prompt": True, "reason": "Both insert elements digitally. Cut/paste = onto authentic doc; scanned = onto a scan of authentic doc. Subtle distinction."},
            {"source": "digital_desktop", "target": "digital_scanned", "strength": 0.6, "severity": "MEDIUM", "from_prompt": True, "reason": "Both software-generated. Desktop = built from scratch; scanned = built over a real scan as base."},
            {"source": "addition_insertion", "target": "erasure_chemical", "strength": 0.65, "severity": "MEDIUM", "from_prompt": True, "reason": "Both alter character meaning. Insertion = add ink (paper intact); erasure = remove + replace (paper damaged)."},
            {"source": "addition_insertion", "target": "erasure_mechanical", "strength": 0.65, "severity": "MEDIUM", "from_prompt": True, "reason": "Same logic, paper damage distinguishes erasure from insertion."},
            {"source": "erasure_chemical", "target": "erasure_mechanical", "strength": 0.8, "severity": "HIGH", "from_prompt": True, "reason": "Both remove + replace. Chemical = solvent (smooth, stained); mechanical = abrasion (rough, fuzzy fibers)."},
            {"source": "erasure_chemical", "target": "obliteration_ink", "strength": 0.7, "severity": "MEDIUM", "from_prompt": True, "reason": "Both can show ink smudges. Erasure smudge = at EDGE of blank where char used to be. Obliteration = covering text intentionally."},
            {"source": "obliteration_ink", "target": "obliteration_whiteout", "strength": 0.5, "severity": "LOW", "from_prompt": False, "reason": "Both cover text. Different materials but only 5 words of detail each, model has minimal cues to distinguish."},
        ],
        "variables": [
            {"name": "document_type", "desc": "Type of document (passport, check, contract, ID, etc.). Selected from a fixed list.", "influence": "Activates document-specific rules (e.g., bank check rule, ID security features). Strong nudge toward category-relevant indicators."},
            {"name": "suspicion_reason", "desc": "User's free-text description of why they suspect forgery (max 300 chars).", "influence": "Free text bias. Can mention specific words like 'erased', 'pasted', 'traced' that anchor classification. The prompt explicitly tells the model to verify against image."},
            {"name": "area_of_concern", "desc": "Where the user wants the model to focus (e.g., 'signature', 'date field').", "influence": "Directs attention. Doesn't force a category but biases toward forgery types common in that region."},
            {"name": "image_source", "desc": "Phone photo / scan / screenshot / not sure.", "influence": "Strong influence. Screenshot leans digital_desktop. Phone photo leans physical forgeries."},
            {"name": "is_forged_belief", "desc": "User believes it IS forged / NOT forged / not sure.", "influence": "Weak suggestion. Prompt warns model not to be pressured by user's belief, must verify against image."},
            {"name": "shot_type", "desc": "Close-up / full document / not sure.", "influence": "Affects what evidence is visible. Close-up = micro-tremors, fiber details. Full doc = layout, font consistency."},
            {"name": "lighting", "desc": "Natural / raking / bright / not sure.", "influence": "Critical for sympathetic_indented (needs raking light) and erasure detection (oblique light shows sheen)."},
            {"name": "physical_clues", "desc": "Specific clue user thinks they observed (16 options: indentation_grooves, carbon_streaks, ink_halo, paper_thinning, etc.).", "influence": "STRONGEST per-variable bias. Each clue maps to a category. The prompt tells the model to verify but it nudges hard."},
        ],
    }
