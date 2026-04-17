"""
ForgeGuard Document Forensics API
=================================
AI-powered document forgery detection system

Categories:
1. Traced (3 classes): carbon, indentation, projection
2. Alteration (4 classes): addition_insertion, addition_interlineation, erasure_chemical, erasure_mechanical
3. Digital (3 classes): cut_paste, desktop_publishing, scanned
4. Obliteration (3 classes): ink_stroke, whiteout, opaque_pigment
5. Sympathetic Ink (2 classes): indented_writing, special_ink
6. Currency (1 class): currency_analysis

Total: 16 YOLO classes
"""

import os
import io
import json
import random
import string
import base64
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from PIL import Image

# Load environment variables
load_dotenv()

# ============================================
# CONFIGURATION
# ============================================

# LLM Settings
USE_CLOUD_LLM = os.getenv("USE_CLOUD_LLM", "false").lower() == "true"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

# YOLO Settings
YOLO_WEIGHTS_PATH = os.getenv("YOLO_WEIGHTS_PATH", "./weights/best.pt")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.25"))

# ============================================
# CLASS LABELS - Map YOLO class indices to labels
# Update this when you train your own model!
# ============================================

CLASS_LABELS = {
    # Traced (0-2)
    0: {"name": "traced_carbon", "title": "Carbon Transfer", "category": "Traced", "color": "#3b82f6"},
    1: {"name": "traced_indentation", "title": "Indentation/Canal Light", "category": "Traced", "color": "#3b82f6"},
    2: {"name": "traced_projection", "title": "Projection Process", "category": "Traced", "color": "#3b82f6"},
    
    # Alteration (3-6)
    3: {"name": "addition_insertion", "title": "Addition: Insertion", "category": "Alteration", "color": "#dc2626"},
    4: {"name": "addition_interlineation", "title": "Addition: Interlineation", "category": "Alteration", "color": "#dc2626"},
    5: {"name": "erasure_chemical", "title": "Erasure: Chemical", "category": "Alteration", "color": "#dc2626"},
    6: {"name": "erasure_mechanical", "title": "Erasure: Mechanical", "category": "Alteration", "color": "#dc2626"},
    
    # Digital (7-9)
    7: {"name": "digital_cut_paste", "title": "Cut and Paste", "category": "Digital", "color": "#8b5cf6"},
    8: {"name": "digital_desktop", "title": "Desktop Publishing", "category": "Digital", "color": "#8b5cf6"},
    9: {"name": "digital_scanned", "title": "Scanned Documents", "category": "Digital", "color": "#8b5cf6"},
    
    # Obliteration (10-12)
    10: {"name": "obliteration_ink", "title": "Ink Stroke", "category": "Obliteration", "color": "#f97316"},
    11: {"name": "obliteration_whiteout", "title": "White Out", "category": "Obliteration", "color": "#f97316"},
    12: {"name": "obliteration_pigment", "title": "Opaque Pigment", "category": "Obliteration", "color": "#f97316"},
    
    # Sympathetic Ink (13-14)
    13: {"name": "sympathetic_indented", "title": "Indented Writing", "category": "Sympathetic Ink", "color": "#22c55e"},
    14: {"name": "sympathetic_special", "title": "Special Ink", "category": "Sympathetic Ink", "color": "#22c55e"},
    
    # Currency (15)
    15: {"name": "currency_analysis", "title": "Currency Forgery", "category": "Currency", "color": "#eab308"},
}

# ============================================
# TRAINING STATUS - Track which categories have trained data
# This is for HONEST error prevention!
# Update this after training each category.
# ============================================

TRAINING_STATUS = {
    # Set to True ONLY after you've trained with real data for that class
    # This controls whether the system admits uncertainty
    
    # Traced
    "traced_carbon": False,
    "traced_indentation": False,
    "traced_projection": False,
    
    # Alteration
    "addition_insertion": False,
    "addition_interlineation": False,
    "erasure_chemical": False,
    "erasure_mechanical": False,
    
    # Digital - These have some public data available
    "digital_cut_paste": True,      # Can use CASIA/Roboflow
    "digital_desktop": False,        # NO public data - needs client samples
    "digital_scanned": False,        # NO public data - needs client samples
    
    # Obliteration
    "obliteration_ink": False,
    "obliteration_whiteout": False,
    "obliteration_pigment": False,
    
    # Sympathetic Ink
    "sympathetic_indented": False,
    "sympathetic_special": False,
    
    # Currency
    "currency_analysis": False,
}

# Confidence thresholds for honest reporting
CONFIDENCE_THRESHOLDS = {
    "high": 0.75,      # High confidence - model is sure
    "medium": 0.50,    # Medium confidence - somewhat certain
    "low": 0.25,       # Low confidence - uncertain, needs more training
}

# ============================================
# HELPER: Generate honest warnings
# ============================================

def get_training_warning(category: Optional[str], detections: List[Dict]) -> Optional[str]:
    """
    Generate honest warning if:
    1. Category hasn't been trained with real data
    2. Confidence is low
    3. No detections but category was specified
    
    This is the ERROR PREVENTION the user asked for!
    """
    warnings = []
    
    # Check if specific category was requested
    if category:
        is_trained = TRAINING_STATUS.get(category, False)
        if not is_trained:
            warnings.append(
                f"⚠️ LIMITED TRAINING DATA: The '{category}' category has not been "
                f"trained with sufficient real-world samples. Results may be unreliable. "
                f"This model needs more training data for accurate detection of this forgery type."
            )
    
    # Check overall model training status
    trained_categories = sum(1 for v in TRAINING_STATUS.values() if v)
    total_categories = len(TRAINING_STATUS)
    
    if trained_categories == 0:
        warnings.append(
            "⚠️ MODEL NOT TRAINED: This model has not been trained on any forgery categories yet. "
            "All results are placeholder/demo only. Train the model with labeled data first."
        )
    elif trained_categories < total_categories:
        untrained = [k for k, v in TRAINING_STATUS.items() if not v]
        if len(untrained) <= 5:
            warnings.append(
                f"ℹ️ PARTIAL TRAINING: The following categories lack training data: "
                f"{', '.join(untrained[:5])}{'...' if len(untrained) > 5 else ''}. "
                f"Detection accuracy for these types may be limited."
            )
    
    # Check detection confidence
    if detections:
        avg_conf = sum(d["confidence"] for d in detections) / len(detections)
        if avg_conf < CONFIDENCE_THRESHOLDS["medium"]:
            warnings.append(
                f"⚠️ LOW CONFIDENCE: Average detection confidence is {avg_conf:.1%}. "
                f"Results are uncertain. Consider physical examination by a forensic expert."
            )
    elif category:
        # No detections for a specific category
        is_trained = TRAINING_STATUS.get(category, False)
        if not is_trained:
            warnings.append(
                f"ℹ️ NO DETECTION: No forgery detected for '{category}', but this category "
                f"has limited training data. The model may have missed indicators."
            )
    
    return " | ".join(warnings) if warnings else None

# Reverse lookup: name -> class_id
NAME_TO_CLASS = {v["name"]: k for k, v in CLASS_LABELS.items()}

# Valid API keys for categories
VALID_CATEGORIES = list(NAME_TO_CLASS.keys())

# ============================================
# RESPONSE MODELS
# ============================================

class Coordinates(BaseModel):
    x_min: int
    y_min: int
    x_max: int
    y_max: int

class Annotation(BaseModel):
    id: int
    type: str = "bounding_box"
    coordinates: Coordinates
    color: str
    title: str
    confidence: float

class ImageDimensions(BaseModel):
    width: int
    height: int

class AnalysisResponse(BaseModel):
    scan_id: str
    category_analyzed: Optional[str]
    verdict: str  # "forged", "suspicious", "genuine"
    confidence_score: float
    llm_explanation: str
    annotations: List[Annotation]
    original_image_dimensions: ImageDimensions
    timestamp: str
    # NEW: Honest warning about training data limitations
    training_warning: Optional[str] = None
    # NEW: Training status for the analyzed category
    category_trained: bool = False

class HealthResponse(BaseModel):
    status: str
    llm_mode: str
    yolo_loaded: bool
    version: str

# ============================================
# YOLO MODELS - One per forgery type (16 total)
# ============================================

# Dictionary to hold all loaded models
yolo_models = {}

# Path to models directory
MODELS_DIR = Path(__file__).parent / "models"

def load_yolo_models():
    """
    Load all available YOLO models.
    Each forgery type has its own specialist model.
    
    Models are loaded from: models/<type>/weights/best.pt
    """
    global yolo_models
    
    try:
        from ultralytics import YOLO
    except ImportError:
        print("❌ ultralytics not installed. Run: pip install ultralytics")
        return False
    
    loaded_count = 0
    
    # Load model for each forgery type that has trained weights
    for type_name in TRAINING_STATUS.keys():
        weights_path = MODELS_DIR / type_name / "weights" / "best.pt"
        
        if weights_path.exists():
            try:
                yolo_models[type_name] = YOLO(str(weights_path))
                TRAINING_STATUS[type_name] = True  # Mark as trained
                loaded_count += 1
                print(f"  ✓ Loaded: {type_name}")
            except Exception as e:
                print(f"  ✗ Failed: {type_name} - {e}")
        else:
            # No weights yet
            TRAINING_STATUS[type_name] = False
    
    print(f"\n  Models loaded: {loaded_count}/{len(TRAINING_STATUS)}")
    
    # If no models loaded, load a default yolov8n for demo purposes
    if loaded_count == 0:
        print("  ℹ️  No trained models found. Loading base yolov8n for demo.")
        try:
            yolo_models["_default"] = YOLO("yolov8n.pt")
        except Exception as e:
            print(f"  ✗ Could not load default model: {e}")
            return False
    
    return True


def get_model_for_category(category: Optional[str] = None):
    """
    Get the appropriate model for a category.
    
    Args:
        category: Specific forgery type (e.g., 'digital_cut_paste')
                  If None, returns default model for general detection
    
    Returns:
        YOLO model or None if not available
    """
    if category and category in yolo_models:
        return yolo_models[category]
    
    # Return default if available
    return yolo_models.get("_default")

# ============================================
# LLM FUNCTIONS
# ============================================

def build_llm_prompt(detections: List[Dict], category: Optional[str] = None) -> str:
    """Build prompt for LLM explanation"""
    
    if not detections:
        return """You are a forensic document examiner AI. The image analysis found no clear signs of forgery.
        
Provide a brief professional statement (2-3 sentences) indicating that no obvious forgery indicators were detected, 
but recommend physical examination for certainty. Keep it concise and professional."""
    
    detection_summary = []
    for det in detections:
        detection_summary.append(f"- {det['title']} (confidence: {det['confidence']:.0%})")
    
    category_context = f" specifically for {category} type forgery" if category else ""
    
    return f"""You are a forensic document examiner AI. Analyze these detection results{category_context}:

Detections found:
{chr(10).join(detection_summary)}

Provide a professional forensic analysis explanation in 3-4 sentences:
1. Summarize what was detected
2. Explain what these indicators typically mean
3. State the likely conclusion about document authenticity
4. Recommend next steps if applicable

Be concise, professional, and avoid speculation beyond the evidence."""

def call_ollama_api(prompt: str) -> str:
    """Call local Ollama API"""
    import requests
    
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 256,
                }
            },
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json().get("response", "Analysis complete.")
        else:
            print(f"Ollama error: {response.status_code}")
            return None
    except Exception as e:
        print(f"Ollama API error: {e}")
        return None

def call_groq_api(prompt: str) -> str:
    """Call Groq Cloud API"""
    try:
        from groq import Groq
        
        client = Groq(api_key=GROQ_API_KEY)
        
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a forensic document examiner AI assistant."},
                {"role": "user", "content": prompt}
            ],
            model=GROQ_MODEL,
            temperature=0.7,
            max_tokens=256,
        )
        
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"Groq API error: {e}")
        return None

def get_llm_explanation(detections: List[Dict], category: Optional[str] = None) -> str:
    """Get LLM explanation with fallback"""
    
    prompt = build_llm_prompt(detections, category)
    
    # Try configured LLM
    if USE_CLOUD_LLM and GROQ_API_KEY:
        result = call_groq_api(prompt)
        if result:
            return result
    else:
        result = call_ollama_api(prompt)
        if result:
            return result
    
    # Fallback: generate basic explanation from detections
    if not detections:
        return "Forensic analysis complete. No clear forgery indicators were detected in the examined document. However, physical examination by a certified forensic document examiner is recommended for conclusive authentication."
    
    titles = [d["title"] for d in detections]
    return f"Forensic analysis detected potential forgery indicators: {', '.join(titles)}. These findings suggest the document may have been altered or manipulated. Further examination by a certified forensic document examiner is recommended."

# ============================================
# HELPER FUNCTIONS
# ============================================

def generate_scan_id() -> str:
    """Generate unique scan ID"""
    timestamp = datetime.now().strftime("%Y%m%d")
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"FG-{timestamp}-{random_part}"

def determine_verdict(detections: List[Dict]) -> tuple[str, float]:
    """Determine verdict based on detections"""
    
    if not detections:
        return "genuine", 0.15
    
    # Get max confidence from detections
    max_conf = max(d["confidence"] for d in detections)
    avg_conf = sum(d["confidence"] for d in detections) / len(detections)
    
    # Weighted confidence
    confidence = (max_conf * 0.7) + (avg_conf * 0.3)
    
    if confidence >= 0.75:
        return "forged", confidence
    elif confidence >= 0.50:
        return "suspicious", confidence
    else:
        return "genuine", confidence

def run_yolo_inference(image: Image.Image, category: Optional[str] = None) -> List[Dict]:
    """
    Run YOLO inference on image using specialist models.
    
    If category is specified: Use that specific model (binary classifier)
    If category is None: Run ALL available models to detect any forgery type
    
    Each model is a binary classifier that outputs:
    - Class 0: <type>_detected (e.g., digital_cut_paste_detected)
    """
    
    detections = []
    
    # Determine which models to run
    if category:
        # Specific category requested - use that model only
        models_to_run = {category: yolo_models.get(category)}
        if models_to_run[category] is None:
            # No trained model for this category - use default if available
            default_model = yolo_models.get("_default")
            if default_model:
                models_to_run = {"_default": default_model}
            else:
                return []
    else:
        # No category specified - run ALL trained models
        models_to_run = {k: v for k, v in yolo_models.items() if k != "_default"}
        
        # If no trained models, use default
        if not models_to_run:
            default_model = yolo_models.get("_default")
            if default_model:
                models_to_run = {"_default": default_model}
            else:
                return []
    
    # Run inference with each model
    for model_name, model in models_to_run.items():
        if model is None:
            continue
            
        try:
            results = model(image, conf=CONFIDENCE_THRESHOLD, verbose=False)
            
            for result in results:
                boxes = result.boxes
                
                for i, box in enumerate(boxes):
                    class_id = int(box.cls[0])
                    confidence = float(box.conf[0])
                    
                    # Get coordinates
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    
                    # For specialist models, the class_id is always 0
                    # The model_name tells us what type of forgery was detected
                    if model_name != "_default":
                        # This is a specialist model - use model_name as the type
                        type_name = model_name
                        class_info = CLASS_LABELS.get(NAME_TO_CLASS.get(type_name, -1), {
                            "name": type_name,
                            "title": type_name.replace("_", " ").title(),
                            "category": "Unknown",
                            "color": "#dc2626"
                        })
                    else:
                        # Default model - use class_id from model
                        class_info = CLASS_LABELS.get(class_id, {
                            "name": f"class_{class_id}",
                            "title": f"Detection {class_id}",
                            "category": "Unknown",
                            "color": "#dc2626"
                        })
                    
                    detections.append({
                        "id": len(detections) + 1,
                        "class_id": NAME_TO_CLASS.get(class_info["name"], class_id),
                        "confidence": confidence,
                        "title": class_info["title"],
                        "category": class_info["category"],
                        "color": class_info["color"],
                        "model_used": model_name,
                        "coordinates": {
                            "x_min": x1,
                            "y_min": y1,
                            "x_max": x2,
                            "y_max": y2
                        }
                    })
        
        except Exception as e:
            print(f"YOLO inference error ({model_name}): {e}")
            continue
    
    # Sort by confidence
    detections.sort(key=lambda x: x["confidence"], reverse=True)
    
    return detections

# ============================================
# FASTAPI APP
# ============================================

app = FastAPI(
    title="ForgeGuard API",
    description="AI-powered document forgery detection",
    version="2.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# STARTUP
# ============================================

@app.on_event("startup")
async def startup_event():
    """Initialize models on startup"""
    print("\n" + "="*50)
    print("ForgeGuard API Starting...")
    print("="*50)
    
    # Load YOLO models (16 specialist models)
    print("\n📦 Loading YOLO models...")
    yolo_loaded = load_yolo_models()
    
    trained_count = sum(1 for v in TRAINING_STATUS.values() if v)
    print(f"\n✓ Models ready: {trained_count}/16 trained")
    
    # LLM mode
    llm_mode = "Groq Cloud" if USE_CLOUD_LLM else "Local Ollama"
    print(f"✓ LLM Mode: {llm_mode}")
    
    print(f"✓ Total forgery types: {len(CLASS_LABELS)}")
    print("="*50 + "\n")

# ============================================
# ENDPOINTS
# ============================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    
    # Count loaded models
    loaded_models = len([m for m in yolo_models.values() if m is not None])
    trained_types = sum(1 for v in TRAINING_STATUS.values() if v)
    
    return HealthResponse(
        status="healthy",
        llm_mode="groq" if USE_CLOUD_LLM else "ollama",
        yolo_loaded=loaded_models > 0,
        version="2.0.0"
    )

@app.get("/categories")
async def get_categories():
    """Get all available categories and classes with training status"""
    categories = {}
    
    for class_id, info in CLASS_LABELS.items():
        cat = info["category"]
        if cat not in categories:
            categories[cat] = []
        
        # Include training status for honest reporting
        is_trained = TRAINING_STATUS.get(info["name"], False)
        
        categories[cat].append({
            "class_id": class_id,
            "api_key": info["name"],
            "title": info["title"],
            "color": info["color"],
            "is_trained": is_trained,  # NEW: Show if this class has training data
            "training_note": "Ready" if is_trained else "Needs training data"
        })
    
    # Summary statistics
    trained_count = sum(1 for v in TRAINING_STATUS.values() if v)
    total_count = len(TRAINING_STATUS)
    
    return {
        "categories": categories, 
        "total_classes": len(CLASS_LABELS),
        "training_summary": {
            "trained": trained_count,
            "untrained": total_count - trained_count,
            "total": total_count,
            "percentage_ready": f"{(trained_count / total_count) * 100:.0f}%"
        }
    }

@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_document(
    imageFile: UploadFile = File(...),
    category: Optional[str] = Form(None)
):
    """Analyze document for forgery"""
    
    # Validate category if provided
    if category and category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid category. Valid options: {VALID_CATEGORIES}"
        )
    
    # Read and validate image
    try:
        image_data = await imageFile.read()
        image = Image.open(io.BytesIO(image_data))
        
        # Convert to RGB if necessary
        if image.mode != "RGB":
            image = image.convert("RGB")
        
        width, height = image.size
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {str(e)}")
    
    # Run YOLO inference
    detections = run_yolo_inference(image, category)
    
    # Determine verdict
    verdict, confidence = determine_verdict(detections)
    
    # Get LLM explanation
    llm_explanation = get_llm_explanation(detections, category)
    
    # Get honest training warning (ERROR PREVENTION!)
    training_warning = get_training_warning(category, detections)
    
    # Check if category is trained
    category_trained = TRAINING_STATUS.get(category, False) if category else False
    
    # Build annotations
    annotations = [
        Annotation(
            id=det["id"],
            type="bounding_box",
            coordinates=Coordinates(**det["coordinates"]),
            color=det["color"],
            title=det["title"],
            confidence=det["confidence"]
        )
        for det in detections
    ]
    
    # Build response with honest warnings
    return AnalysisResponse(
        scan_id=generate_scan_id(),
        category_analyzed=category,
        verdict=verdict,
        confidence_score=confidence,
        llm_explanation=llm_explanation,
        annotations=annotations,
        original_image_dimensions=ImageDimensions(width=width, height=height),
        timestamp=datetime.now().isoformat(),
        training_warning=training_warning,
        category_trained=category_trained
    )

@app.post("/preliminary")
async def preliminary_scan(imageFile: UploadFile = File(...)):
    """Quick scan to suggest likely forgery categories"""
    
    # Read image
    try:
        image_data = await imageFile.read()
        image = Image.open(io.BytesIO(image_data))
        if image.mode != "RGB":
            image = image.convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {str(e)}")
    
    # Run inference without category filter
    detections = run_yolo_inference(image, None)
    
    # Group by category
    category_scores = {}
    for det in detections:
        cat = det["category"]
        if cat not in category_scores:
            category_scores[cat] = {"count": 0, "max_confidence": 0}
        category_scores[cat]["count"] += 1
        category_scores[cat]["max_confidence"] = max(
            category_scores[cat]["max_confidence"], 
            det["confidence"]
        )
    
    # Sort by confidence
    suggestions = [
        {"category": cat, "confidence": scores["max_confidence"], "detections": scores["count"]}
        for cat, scores in category_scores.items()
    ]
    suggestions.sort(key=lambda x: x["confidence"], reverse=True)
    
    return {
        "suggestions": suggestions[:3],
        "total_detections": len(detections)
    }

# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
