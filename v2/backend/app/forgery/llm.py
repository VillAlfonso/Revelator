"""
LLM explanation generation.
Takes a Gemini classification result and generates a plain-language forensic summary.
Primary: Groq API. Fallback: Ollama.
"""

import base64
import io
from typing import Optional, Dict

from PIL import Image

from ..config import USE_CLOUD_LLM, GROQ_API_KEY, GROQ_MODEL, GROQ_VISION_MODEL, OLLAMA_URL, OLLAMA_MODEL


def _build_prompt(gemini: Dict) -> str:
    cat = (gemini.get("category_label") or gemini.get("category") or "unknown").replace("_", " ")
    conf = gemini.get("confidence", 0)
    evidence = gemini.get("evidence") or []
    explanation = gemini.get("explanation") or ""
    tools = gemini.get("tools_likely_used") or ""

    evidence_lines = "\n".join(f"- {e}" for e in evidence) if evidence else "- No specific evidence listed."

    return (
        f"You are a forensic document examiner AI. Gemini Vision has analysed a document and produced the following findings:\n\n"
        f"Classification: {cat}\n"
        f"Confidence: {conf:.0%}\n"
        f"Evidence observed:\n{evidence_lines}\n"
        f"Summary: {explanation}\n"
        f"Tools likely used: {tools}\n\n"
        "Using these findings, write a clear 3-4 sentence forensic explanation suitable for a non-expert. "
        "Describe what was detected, what it means, and what the recommended next step is. "
        "Do not fabricate details beyond what is listed above."
    )


def _b64_image(image: Image.Image) -> str:
    buf = io.BytesIO()
    img = image.copy().convert("RGB")
    img.thumbnail((896, 896), Image.LANCZOS)
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def call_groq_vision_api(prompt: str, image: Image.Image) -> Optional[str]:
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        b64 = _b64_image(image)
        chat = client.chat.completions.create(
            model=GROQ_VISION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }],
            temperature=0.4,
            max_tokens=600,
        )
        return (chat.choices[0].message.content or "").strip() or None
    except Exception as e:
        print(f"Groq vision API error: {e}")
        return None


def call_groq_api(prompt: str) -> Optional[str]:
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        chat = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a forensic document examiner AI assistant."},
                {"role": "user", "content": prompt},
            ],
            model=GROQ_MODEL,
            temperature=0.7,
            max_tokens=256,
        )
        return chat.choices[0].message.content
    except Exception as e:
        print(f"Groq API error: {e}")
        return None


def call_ollama_api(prompt: str) -> Optional[str]:
    import requests
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.7, "num_predict": 256}},
            timeout=180,
        )
        if response.status_code == 200:
            return response.json().get("response", "Analysis complete.")
    except Exception as e:
        print(f"Ollama API error: {e}")
    return None


def get_llm_explanation(gemini: Dict, image: Optional[Image.Image] = None) -> Optional[str]:
    prompt = _build_prompt(gemini)

    if USE_CLOUD_LLM and GROQ_API_KEY:
        if image is not None:
            result = call_groq_vision_api(prompt, image)
            if result:
                return result
        result = call_groq_api(prompt)
        if result:
            return result
    else:
        result = call_ollama_api(prompt)
        if result:
            return result

    return None
