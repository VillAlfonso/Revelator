"""Document type definitions for forensic scanning.

Maps document types to applicable forgery categories to help guide
Gemini Vision classification."""

DOCUMENT_TYPES = {
    "passport": {
        "title": "Passport",
        "description": "Official travel document with photo, signature, and security features",
        "applicable_categories": [
            "traced_carbon", "traced_indentation", "traced_projection",
            "addition_insertion", "addition_interlineation", "erasure_chemical", "erasure_mechanical",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
            "obliteration_ink", "obliteration_whiteout", "obliteration_pigment",
            "sympathetic_indented", "sympathetic_special",
        ],
    },
    "driver_license": {
        "title": "Driver's License",
        "description": "Government-issued identification with photo, signature, and number",
        "applicable_categories": [
            "traced_carbon", "traced_indentation", "traced_projection",
            "addition_insertion", "addition_interlineation", "erasure_chemical", "erasure_mechanical",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
            "obliteration_ink", "obliteration_whiteout", "obliteration_pigment",
        ],
    },
    "bank_check": {
        "title": "Bank Check",
        "description": "Financial instrument with signature, routing numbers, and account details",
        "applicable_categories": [
            "traced_carbon", "traced_indentation", "traced_projection",
            "addition_insertion", "addition_interlineation", "erasure_chemical", "erasure_mechanical",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
            "obliteration_ink", "obliteration_whiteout", "obliteration_pigment",
            "sympathetic_indented",
        ],
    },
    "contract": {
        "title": "Contract/Agreement",
        "description": "Legal document with signatures, dates, and terms",
        "applicable_categories": [
            "traced_carbon", "traced_indentation", "traced_projection",
            "addition_insertion", "addition_interlineation", "erasure_chemical", "erasure_mechanical",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
            "obliteration_ink", "obliteration_whiteout", "obliteration_pigment",
            "sympathetic_indented", "sympathetic_special",
        ],
    },
    "certificate": {
        "title": "Certificate/Diploma",
        "description": "Educational or professional credential with signatures and seals",
        "applicable_categories": [
            "traced_carbon", "traced_indentation", "traced_projection",
            "addition_insertion", "addition_interlineation", "erasure_chemical", "erasure_mechanical",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
            "obliteration_ink", "obliteration_whiteout", "obliteration_pigment",
            "sympathetic_indented", "sympathetic_special",
        ],
    },
    "invoice": {
        "title": "Invoice/Receipt",
        "description": "Business document with amounts, dates, and signatures",
        "applicable_categories": [
            "addition_insertion", "addition_interlineation", "erasure_chemical", "erasure_mechanical",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
            "obliteration_ink", "obliteration_whiteout", "obliteration_pigment",
        ],
    },
    "signature": {
        "title": "Signature Document",
        "description": "Document primarily for signature authentication (form, affidavit, etc.)",
        "applicable_categories": [
            "traced_carbon", "traced_indentation", "traced_projection",
            "digital_cut_paste",
            "obliteration_ink", "obliteration_whiteout", "obliteration_pigment",
            "sympathetic_indented", "sympathetic_special",
        ],
    },
    "id_card": {
        "title": "ID Card",
        "description": "National or organizational identity card with photo and number",
        "applicable_categories": [
            "traced_carbon", "traced_indentation", "traced_projection",
            "addition_insertion", "addition_interlineation", "erasure_chemical", "erasure_mechanical",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
            "obliteration_ink", "obliteration_whiteout", "obliteration_pigment",
        ],
    },
    "currency": {
        "title": "Currency/Banknote",
        "description": "Paper money or banknote",
        "applicable_categories": [
            "currency_analysis",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
        ],
    },
    "medical_record": {
        "title": "Medical Record",
        "description": "Doctor's notes, prescription, or medical certificate",
        "applicable_categories": [
            "traced_carbon", "traced_indentation", "traced_projection",
            "addition_insertion", "addition_interlineation", "erasure_chemical", "erasure_mechanical",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
            "obliteration_ink", "obliteration_whiteout", "obliteration_pigment",
            "sympathetic_indented",
        ],
    },
    "power_of_attorney": {
        "title": "Power of Attorney",
        "description": "Legal authorization document with witness and notary signatures",
        "applicable_categories": [
            "traced_carbon", "traced_indentation", "traced_projection",
            "addition_insertion", "addition_interlineation", "erasure_chemical", "erasure_mechanical",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
            "obliteration_ink", "obliteration_whiteout", "obliteration_pigment",
            "sympathetic_indented", "sympathetic_special",
        ],
    },
    "other": {
        "title": "Other Document",
        "description": "Any other type of document not listed above",
        "applicable_categories": [
            "traced_carbon", "traced_indentation", "traced_projection",
            "addition_insertion", "addition_interlineation", "erasure_chemical", "erasure_mechanical",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
            "obliteration_ink", "obliteration_whiteout", "obliteration_pigment",
            "sympathetic_indented", "sympathetic_special",
            "currency_analysis",
        ],
    },
}


def get_document_types_response():
    """Return document types in frontend-friendly format."""
    return {
        "document_types": [
            {
                "key": key,
                "title": info["title"],
                "description": info["description"],
                "applicable_categories": info["applicable_categories"],
            }
            for key, info in DOCUMENT_TYPES.items()
        ]
    }
