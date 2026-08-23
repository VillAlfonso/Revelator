from app.forgery.gemini_vision import _extract_pasted_analysis_hints


def test_extract_pasted_analysis_hints_parses_report_style_text():
    text = """
    Document Analysis

    Document Type:
    Passport (Philippine e-Passport)

    Genuine or Forged:
    Genuine

    Forgery Category:
    None

    Confidence Level:
    High

    Key Evidence:
    - Visible holographic security features
    - Properly formatted MRZ
    - Official issuing authority shown as DFA SAN PABLO

    Brief Reasoning:
    The passport displays standard security features.
    """

    hints = _extract_pasted_analysis_hints(text)

    assert any("Document type appears to be" in hint for hint in hints)
    assert any("classifies the document as" in hint for hint in hints)
    assert any("Forgery category" in hint for hint in hints)
    assert any("Evidence cues" in hint for hint in hints)
