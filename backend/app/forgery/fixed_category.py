"""Prompt for a fixed-category explanation."""


def explanation_prompt(category, label):
    return f"""Explain the image under this fixed classification: {category} ({label}).
This is an explanation task, not an open-ended category-selection task.
Keep this category throughout the explanation, evidence and reasoning steps.
Do not substitute a new verdict such as "No Forgery Detected" unless that is
itself the fixed classification. Describe missing detail as a visual limitation,
not as a replacement category.
Examine the image details and find visible evidence supporting this category.
Return JSON with category, subtype, confidence, explanation, evidence (list),
reasoning_steps (list of concise observations), anomaly_location,
tools_likely_used and alternatives (empty list).
Use exactly {category} in category. Begin explanation with {label}.
Confidence must measure visible support for THIS category, not another verdict.
Do not invent evidence or force a justification when features are not visible.
If evidence is insufficient, describe the limitation and use low confidence.
Do not mention admin selection, intercept, datasets, folder labels or constraints.
All fields must describe the same category without a contradictory verdict.
"""
