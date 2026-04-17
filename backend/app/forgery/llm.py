"""
LLM explanation generation (extracted from original main.py).
"""

from typing import Optional, List, Dict
from ..config import USE_CLOUD_LLM, GROQ_API_KEY, GROQ_MODEL, OLLAMA_URL, OLLAMA_MODEL


def build_llm_prompt(detections: List[Dict], category: Optional[str] = None) -> str:
    if not detections:
        return (
            "You are a forensic document examiner AI. The image analysis found no clear signs of forgery.\n"
            "Provide a brief professional statement (2-3 sentences) indicating that no obvious forgery "
            "indicators were detected, but recommend physical examination for certainty."
        )

    detection_summary = [f"- {d['title']} (confidence: {d['confidence']:.0%})" for d in detections]
    category_context = f" specifically for {category} type forgery" if category else ""

    return (
        f"You are a forensic document examiner AI. Analyze these detection results{category_context}:\n\n"
        f"Detections found:\n" + "\n".join(detection_summary) + "\n\n"
        "Provide a professional forensic analysis explanation in 3-4 sentences:\n"
        "1. Summarize what was detected\n"
        "2. Explain what these indicators typically mean\n"
        "3. State the likely conclusion about document authenticity\n"
        "4. Recommend next steps if applicable\n\n"
        "Be concise, professional, and avoid speculation beyond the evidence."
    )


def call_ollama_api(prompt: str) -> Optional[str]:
    import requests
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.7, "num_predict": 256}},
            timeout=30,
        )
        if response.status_code == 200:
            return response.json().get("response", "Analysis complete.")
    except Exception as e:
        print(f"Ollama API error: {e}")
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


def get_llm_explanation(detections: List[Dict], category: Optional[str] = None) -> str:
    prompt = build_llm_prompt(detections, category)

    if USE_CLOUD_LLM and GROQ_API_KEY:
        result = call_groq_api(prompt)
        if result:
            return result
    else:
        result = call_ollama_api(prompt)
        if result:
            return result

    # Fallback
    if not detections:
        return (
            "Forensic analysis complete. No clear forgery indicators were detected. "
            "Physical examination by a certified forensic document examiner is recommended."
        )
    titles = [d["title"] for d in detections]
    return (
        f"Forensic analysis detected potential forgery indicators: {', '.join(titles)}. "
        "Further examination by a certified forensic document examiner is recommended."
    )
