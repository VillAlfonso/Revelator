"""
Model tier definitions for Revelator.

Three tiers of forensic analysis, each progressively more capable:

  ANALYST  — Tier 1 — Gemini Vision only (general-purpose multimodal LLM).
             Available: NOW. Plans: free, pro, premium.

  DETECTIVE — Tier 2 — Fine-tuned LLaVA (100 imgs/category) + Gemini ensemble.
              Available: COMING SOON (stub returns Analyst result for now).
              Plans: pro, premium.

  SHERLOCK — Tier 3 — Fine-tuned LLaVA (500 imgs/category, includes document-type
             training data) + Gemini ensemble + document-type aware reasoning.
             Available: COMING SOON (stub returns Analyst result for now).
             Plans: premium.

The plan-tier mapping is enforced at the analyze endpoint.
"""

from typing import Dict, List

# Tier identifiers (used in API requests/responses)
TIER_ANALYST = "analyst"
TIER_DETECTIVE = "detective"
TIER_SHERLOCK = "sherlock"

ALL_TIERS = [TIER_ANALYST, TIER_DETECTIVE, TIER_SHERLOCK]


# Which tiers are unlocked for each subscription plan.
# Free users get only the Analyst. Pro adds Detective. Premium adds Sherlock.
PLAN_TIERS: Dict[str, List[str]] = {
    "free":    [TIER_ANALYST],
    "pro":     [TIER_ANALYST, TIER_DETECTIVE],
    "premium": [TIER_ANALYST, TIER_DETECTIVE, TIER_SHERLOCK],
}


# Whether each tier's underlying model is actually wired up. Stubs return
# Analyst results when False, so the UI can still preview the tier today.
TIER_AVAILABLE: Dict[str, bool] = {
    TIER_ANALYST:   True,    # Gemini is live
    TIER_DETECTIVE: False,   # LLaVA-100 not yet trained / hosted
    TIER_SHERLOCK:  False,   # LLaVA-500 not yet trained / hosted
}


# Public-facing metadata returned to the frontend so the UI can render the
# tier picker and the About page without hard-coding strings on the client.
TIER_META = {
    TIER_ANALYST: {
        "key": TIER_ANALYST,
        "name": "Analyst",
        "rank": 1,
        "tagline": "General-purpose forensic intuition.",
        "description": (
            "The Analyst uses Google Gemini Vision, a general-purpose multimodal "
            "model trained on a wide swath of internet imagery. It reasons about "
            "documents the way a smart non-specialist would: looking for visible "
            "manipulation, weighing context, and offering a verdict in plain "
            "language. Fast, accessible, and good enough for screening — but not "
            "trained on your specific forgery taxonomy."
        ),
        "models": ["Gemini Vision (gemini-2.5-flash)"],
        "training": (
            "Pre-trained by Google on web-scale multimodal data. Not fine-tuned "
            "on Revelator's forgery dataset. We guide it with a strict system "
            "prompt that defines the 19-category taxonomy."
        ),
        "strengths": [
            "Broad world knowledge",
            "Fast inference (2–5 seconds)",
            "Always available — no warm-up",
        ],
        "limitations": [
            "Not specialized in forensic document analysis",
            "Can hallucinate on subtle forgeries",
            "Sometimes defaults to 'other' when uncertain",
        ],
        "available": True,
        "plans": ["free", "pro", "premium"],
    },
    TIER_DETECTIVE: {
        "key": TIER_DETECTIVE,
        "name": "Detective",
        "rank": 2,
        "tagline": "Specialist trained on 100 examples per forgery type.",
        "description": (
            "The Detective is a fine-tuned LLaVA model, retrained on Revelator's "
            "labeled forensic dataset — roughly 100 images for each of the 16 "
            "forgery categories. Its verdict is then cross-checked by the "
            "Analyst (Gemini) to reduce hallucinations. The two models must "
            "broadly agree before high-confidence is assigned."
        ),
        "models": [
            "LLaVA-NeXT 7B (fine-tuned, 100 imgs/category)",
            "Gemini Vision (verification layer)",
        ],
        "training": (
            "LLaVA-NeXT 7B fine-tuned on Revelator's curated forensic dataset: "
            "~1,600 labeled images total (100 per forgery category × 16 categories). "
            "Trained on Google Colab using LoRA adapters, deployed to Hugging "
            "Face Spaces for free GPU inference. The Gemini layer adds reasoning "
            "and edge-case awareness on top."
        ),
        "strengths": [
            "Domain-specialized — recognizes forgery patterns Gemini misses",
            "Two-model consensus reduces false positives",
            "Better calibrated confidence scores",
        ],
        "limitations": [
            "Slower than Analyst (LLaVA cold start ~10s)",
            "Limited training data per category may miss rare variants",
            "Currently in development — coming soon",
        ],
        "available": False,
        "plans": ["pro", "premium"],
    },
    TIER_SHERLOCK: {
        "key": TIER_SHERLOCK,
        "name": "Sherlock",
        "rank": 3,
        "tagline": "The full forensic stack — every model, every dataset.",
        "description": (
            "Sherlock is the maximum-effort tier. The same fine-tuned LLaVA "
            "architecture as Detective, but trained on 5× the data (500 images "
            "per forgery category) plus dedicated training on each of the 10 "
            "supported document types (passport, bank check, contract, etc.). "
            "This means Sherlock not only knows what forgery looks like — it "
            "knows what an authentic version of *this specific document type* "
            "should look like. Gemini still verifies, providing the final "
            "reasoning layer."
        ),
        "models": [
            "LLaVA-NeXT 7B (fine-tuned, 500 imgs/category + document-type data)",
            "Gemini Vision (verification layer)",
        ],
        "training": (
            "LLaVA-NeXT 7B fine-tuned on Revelator's expanded dataset: ~8,000 "
            "labeled forgery images (500 per category × 16 categories) PLUS "
            "additional training pairs for each document type to teach the "
            "model what authentic passports, checks, contracts, etc. look like. "
            "This gives Sherlock the strongest authenticity baseline of any tier. "
            "Trained on Colab Pro with full fine-tuning, deployed to Hugging "
            "Face Spaces."
        ),
        "strengths": [
            "Highest accuracy of any tier",
            "Knows what authentic documents look like, not just forgeries",
            "Reduces 'no_forgery_detected' false negatives",
            "Document-type aware reasoning",
        ],
        "limitations": [
            "Slowest tier (~15 seconds total inference)",
            "Requires the largest training investment",
            "Currently in development — coming soon",
        ],
        "available": False,
        "plans": ["premium"],
    },
}


def get_allowed_tiers(plan: str) -> List[str]:
    """Return the list of tier keys a user on the given plan may select."""
    return PLAN_TIERS.get(plan, PLAN_TIERS["free"])


def is_tier_allowed(plan: str, tier: str) -> bool:
    """True if a user on `plan` is allowed to use `tier`."""
    return tier in get_allowed_tiers(plan)


def get_tiers_response(user_plan: str | None = None) -> dict:
    """Return tier metadata for the frontend, with `unlocked` flags relative
    to the user's plan if provided."""
    allowed = get_allowed_tiers(user_plan) if user_plan else []
    return {
        "tiers": [
            {
                **meta,
                "unlocked": (meta["key"] in allowed) if user_plan else None,
            }
            for meta in TIER_META.values()
        ],
        "plan_tiers": PLAN_TIERS,
    }
