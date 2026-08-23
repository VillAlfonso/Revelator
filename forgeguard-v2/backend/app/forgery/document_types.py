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
        "title": "Certificate/Diploma/Clearance/Event Participation/Land Title/ID/Passport/Driver License/School ID/PhilHealth",
        "description": "Government, educational, event, land, ID, passport, license, school, and health credentials (DepEd/DECS diplomas including old 1990s Katibayan, university diplomas, NBI Clearances including 2003 forms, PSA CENOMARs, LTFRB Confirmation Certificates, BIR CTCs, LTO OR/CR, Provincial Event Participation Certificates like Amiling Festival, Certificate of Marriage, Old Original Certificate of Title / Free Patent 1980s, PhlPost IDs, PhilID / ePhilID, Driver’s Licenses (LTO), DepEd School IDs, PhilHealth IDs, e-Passports, etc.)",
        "applicable_categories": [
            "traced_carbon", "traced_indentation", "traced_projection",
            "addition_insertion", "addition_interlineation", "erasure_chemical", "erasure_mechanical",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
            "obliteration_ink", "obliteration_whiteout", "obliteration_pigment",
            "sympathetic_indented", "sympathetic_special",
        ],
        "genuine_indicators": [
            "Correct issuing body logos and headers (DepEd Region IV-A, old DECS 1990s branding for elementary Katibayan, BIR Form 0016, LTFRB + DOTC, NBI, PSA, Provincial Government of Laguna for Amiling Festival, National Land Titles and Deeds Registration Administration for old titles, university seals, PhlPost, DFA for passports, LTO for licenses, PhilHealth)",
            "Repeating security background patterns (e.g. 'NATIONAL BUREAU OF INVESTIGATION' on NBI clearances)",
            "Embossed or holographic seals with visible paper interaction and ribbons (gold foil common on diplomas, including old school seals); holographic “PHL” shifting on e-passports; holographic features on LTO licenses",
            "Serial numbers, LRN (12-digit for later docs), Special Order numbers, control/reference numbers, Free Patent numbers, Original Certificate of Title numbers, passport numbers, PRN, License No., PhilHealth Number in correct format for the era",
            "Authorized signatories with exact printed titles (Principal + Board Chairman, Dean + University President, Regional Director, NBI Director including Gen. Reynaldo G. Wycoco in 2003, PSA National Statistician like Claire Dennis S. Mapa, Schools Division Superintendent, Governor like Ramill V. Hernandez, Events Chairman like Pamela Jane P. Baun, President Ferdinand E. Marcos in 1985, Director of Lands Benjamin F. Dumalo, Postmaster General like Joel L. Otarra, LTO Assistant Secretary like Edgar C. Galvante, PhilHealth officials)",
            "Verification mechanisms: QR codes + barcodes, 'Documentary Stamp Tax Paid', 'NO DEROGATORY RECORD', red municipal seals on CTCs, PSA 'not valid if altered' note, MRZ on passports",
            "Bilingual text (Filipino + English) on DepEd documents; old Katibayan in formal Filipino with 'Katibayan' title; old judicial language on land titles",
            "Natural handwriting variation on signatures; physical emboss/hologram reflectance or security printing",
            "Paper aging and period-specific details for old documents (e.g. 1985 land titles with Marcos signature and significant yellowing/aging; 1993 DECS Katibayan; 2003 NBI forms with photo and thumbprint)",
            "Event-specific details for participation certificates: exact event name (Amiling Festival 2025 / Anilag Cosplay), theme, date (March 14, 2025), venue (Time Plaza, Provincial Capitol Compound, Santa Cruz, Laguna)",
            "PhlPost ID specific: photo, address, DOB, PRN, 'PREMIUM' marking, QR code, back disclaimer and barcode",
            "PhilID / ePhilID specific: PSA branding, colorful security background with patterns, QR code, 16-digit number (e.g. 4971-5326-1465-1035 or 3469-2753-1568-0574), photo, address (e.g. CALINGA KARELL AVERION, AUGUST 11, 2004, 452 PUROK 6, SANTIAGO 1, CITY OF SAN PABLO, LAGUNA), DOB, holographic elements",
            "Driver’s License (LTO) specific: LTO branding, security background, holographics, License No. (e.g. D14-22-001444), Agency Code D14, signature of Edgar C. Galvante",
            "DepEd School ID specific: school logo (e.g. Calamba City Science Integrated School 2010), DepEd logo, LRN (e.g. 109814100102), name (e.g. GASTADOR Deen Alpearl G.), grade/section (e.g. 12 ISAROG), school year (e.g. S.Y 2022 - 2023), School ID number (e.g. 308704), photo on plastic card",
            "PhilHealth ID specific: green design, PhilHealth logo, number (e.g. 11-251897314-5), photo, QR code, signature, address, map background",
            "e-Passport specific: secondary facial image, holographic shifting PHL, properly formatted MRZ, DFA issuing office (e.g. DFA San Pablo or DFA Lucena), validity dates (e.g. until August 13, 2033)",
            "Consistent layout matching known genuine templates for the exact document type (NBI Clearance including 2003, PSA CENOMAR, BIR CTC, LTFRB, DepEd/DECS diplomas including old elementary, LTO OR/CR, Provincial Event Participation, Certificate of Marriage, Old Original Certificate of Title / Free Patent 1985, PhlPost ID, PhilID / ePhilID (e.g. 3469-2753-1568-0574), Driver’s License (LTO), DepEd School IDs, PhilHealth IDs, e-Passport, etc.)"
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
        "description": "Paper money or banknote (Philippine Pesos ₱50, ₱100, ₱500, ₱1000, etc.)",
        "applicable_categories": [
            "currency_analysis",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
        ],
        "genuine_indicators": [
            "Correct portraits (e.g. Manuel L. Quezon for ₱20, Sergio Osmeña for ₱50, Manuel A. Roxas for ₱100, Diosdado Macapagal for ₱200, Visayan Spotted Deer for ₱500, appropriate hero for ₱1000), current signatures (President Ferdinand R. Marcos Jr., BSP Governor Eli M. Remolona Jr.)",
            "Serial number format (e.g. CS28040 for ₱20, AP562952 for ₱50, MX345012/MV67490 for ₱100, AL6879411/AM8127695 for ₱500, BN5838335/BN5538335/BV6727980/HZ611893 for ₱1000)",
            "Security features: watermark, security thread, color-shifting denomination, microprinting, proper paper texture; close-up holographic patches show iridescent multi-color shifting (blue/gold/rainbow) with detailed engraving and fine lines that align perfectly",
            "Backs: Banaue Rice Terraces for ₱20, Taal Lake/Tilapia for ₱50, Mayon for ₱100, Chocolate Hills for ₱200, Puerto Princesa Subterranean River (UNESCO) with Blue-naped Parrot for ₱500, Tubbataha Reefs for ₱1000",
            "Under UV light (esp. ₱200 and ₱20): Proper fluorescent security features visible (security threads, fluorescent inks, and patterns). Correct UV reaction patterns. Bright threads and security inks reacting correctly; uniform denomination-specific glow; no irregular glowing, missing elements, or dull response typical of counterfeits. Consistent with authentic BSP-issued notes.",
            "High quality printing, color accuracy, alignment; no poor print, fake holograms, or mismatched elements. Clear UV photos of genuine banknotes with expected fluorescence = genuine (no_forgery_detected).",
            "**Critical for forged specimens**: Many counterfeits include simulated security features (printed thread lines instead of embedded strips, flat/sticker holograms without true iridescent shift or fine engraving, printed shading for 'watermarks', microprint at normal resolution instead of ultra-fine, weak or wrong-color UV response). Do not classify as genuine just because security elements are visibly 'present' — they must be high-fidelity, physically embedded, and optically/fluorescently correct. Notes with all typical features but executed as low-quality simulations = currency forgery."
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
