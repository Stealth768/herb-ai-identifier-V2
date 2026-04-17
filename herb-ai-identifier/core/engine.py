import os
import io
import time
import hashlib
import json
import PIL.Image
import urllib.parse
import urllib.request
import re
import logging
from datetime import datetime
import google.generativeai as genai
from django.conf import settings
from pathlib import Path

# --- GLOBAL CONFIG & LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("HerbAI-Inference")

RESPONSE_CACHE = {}
CACHE_DIR = os.path.join(os.path.dirname(__file__), '.cache')

# --- 1. CACHING SYSTEM (Prevents redundant API hits) ---

def ensure_cache_dir():
    """Ensures the local disk cache directory exists."""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)

def get_cache_key(prompt, image_hash=None):
    """Generates a unique MD5 hash for the specific prompt and image."""
    raw_payload = f"{prompt}_{image_hash}" if image_hash else prompt
    return hashlib.md5(raw_payload.encode()).hexdigest()

def get_cached_response(prompt, image_hash=None):
    """Retrieves a response from memory or disk cache."""
    key = get_cache_key(prompt, image_hash)
    if key in RESPONSE_CACHE:
        return RESPONSE_CACHE[key]
    
    ensure_cache_dir()
    cache_path = os.path.join(CACHE_DIR, f"{key}.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding='utf-8') as f:
                data = json.load(f)
                RESPONSE_CACHE[key] = data["response"]
                return data["response"]
        except Exception as e:
            logger.error(f"Cache read error: {e}")
    return None

def cache_response(prompt, response, image_hash=None):
    """Saves a response to both memory and disk."""
    key = get_cache_key(prompt, image_hash)
    RESPONSE_CACHE[key] = response
    ensure_cache_dir()
    cache_path = os.path.join(CACHE_DIR, f"{key}.json")
    try:
        with open(cache_path, "w", encoding='utf-8') as f:
            json.dump({"response": response, "timestamp": time.time(), "date": str(datetime.now())}, f)
    except Exception as e:
        logger.error(f"Cache write error: {e}")

# --- 2. IMAGE UTILITIES ---

def get_image_hash(image_input):
    """Generates a hash of the image content to identify it in cache."""
    try:
        if isinstance(image_input, str) and os.path.exists(image_input):
            with open(image_input, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        elif isinstance(image_input, PIL.Image.Image):
            buf = io.BytesIO()
            image_input.save(buf, format="JPEG")
            return hashlib.md5(buf.getvalue()).hexdigest()
    except Exception:
        return None
    return None

def preprocess_image(image_input):
    """Standardizes image size to 512x512 to save on API token costs."""
    try:
        if isinstance(image_input, str):
            img = PIL.Image.open(image_input)
        elif isinstance(image_input, PIL.Image.Image):
            img = image_input
        else:
            img = PIL.Image.open(image_input)
        
        img = img.convert("RGB")
        img.thumbnail((512, 512)) # Standardize for token efficiency
        return img
    except Exception as e:
        logger.error(f"Image preprocessing failed: {e}")
        return None

# --- 3. API & MODEL MANAGEMENT (Key Rotator) ---

def get_api_key():
    """Retrieves API Key with support for rotation via comma-separated list."""
    keys = getattr(settings, "GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
    if "," in keys:
        key_list = [k.strip() for k in keys.split(",")]
        # Rotates key based on the current minute
        return key_list[int(time.time() / 60) % len(key_list)]
    return keys

def get_model(model_name="gemini-1.5-flash"):
    """Configures and returns the GenerativeModel instance."""
    api_key = get_api_key()
    if not api_key:
        raise ValueError("No GEMINI_API_KEY found in settings or environment.")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model_name)

# --- 4. DATA FETCHING (Vault & Web) ---

def fetch_local_data(name):
    """Deep-scans the local knowledge_base for matching herb data."""
    try:
        base_dir = getattr(settings, "BASE_DIR", os.path.dirname(os.path.abspath(__file__)))
        kb_path = os.path.join(base_dir, "data", "knowledge_base")
        if not os.path.exists(kb_path):
            os.makedirs(kb_path, exist_ok=True)
            return None
        
        clean_target = "".join(filter(str.isalnum, name)).lower()
        for filename in os.listdir(kb_path):
            if filename.endswith(".txt"):
                # Fuzzy matching: Tulsi.txt matches "Tulsi Plant"
                clean_file = "".join(filter(str.isalnum, filename)).lower()
                if clean_target in clean_file or clean_file in clean_target:
                    with open(os.path.join(kb_path, filename), "r", encoding="utf-8") as f:
                        return f.read(), filename
    except Exception as e:
        logger.error(f"Local fetch error: {e}")
    return None

def fetch_web_image(query):
    """Scrapes a public reference image for the identified herb."""
    try:
        encoded = urllib.parse.quote_plus(f"{query} medicinal plant")
        url = f"https://www.google.com/search?tbm=isch&q={encoded}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as res:
            html = res.read().decode("utf-8", errors="ignore")
        
        # Regex to find high-quality image URLs
        urls = re.findall(r'"(https://[^"]+\.(?:jpg|jpeg|png))"', html)
        for u in urls:
            if "gstatic" not in u and "encrypted" not in u:
                return u
    except Exception:
        pass
    return None

# --- 5. PARSING & ANALYSIS ---

def extract_scientific_name(text):
    """Uses Regex to find botanical names in (Genus species) format."""
    match = re.search(r"\(([A-Z][a-z]+ [a-z]+)\)", text)
    return match.group(1) if match else "N/A"

def call_gemini(image_input, prompt):
    """Executive function to handle API communication with fallback logic."""
    image_hash = get_image_hash(image_input)
    cached = get_cached_response(prompt, image_hash)
    if cached:
        logger.info("Retrieved from cache.")
        return cached

    img_obj = preprocess_image(image_input)
    if not img_obj:
        return "ERROR_IMAGE"

    # Priority 1: Gemini 1.5 Flash (Reliable)
    # Priority 2: Gemini 1.5 Flash-8b (Lightweight fallback)
    for model_tier in ["gemini-1.5-flash", "gemini-1.5-flash-8b"]:
        try:
            model = get_model(model_tier)
            response = model.generate_content([prompt, img_obj])
            
            if response.text:
                cache_response(prompt, response.text, image_hash)
                return response.text
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "quota" in err or "limit" in err:
                logger.warning(f"Tier {model_tier} exhausted. Trying fallback...")
                continue
            logger.error(f"API Error: {e}")
            return "ERROR"
            
    return "QUOTA_EXCEEDED"

def process_full_analysis(image_input):
    """The master pipeline for Herb-AI identification."""
    master_prompt = """
    You are a professional botanical system. Identify this plant specimen.
    Provide the following structure:
    1. Name (Just the common name on the first line)
    2. Scientific Name in parentheses
    3. Botanical Features
    4. Traditional Uses (Unani/Ayurveda)
    5. Health Benefits & Warnings
    """

    raw_result = call_gemini(image_input, master_prompt)

    if raw_result == "QUOTA_EXCEEDED":
        return {
            "name": "Limit Reached",
            "details": "API Quota exceeded. Using local knowledge only.",
            "scientific_name": "N/A",
            "confidence": 0,
            "source": "SYSTEM",
            "matched_image_url": None
        }
    
    if "ERROR" in raw_result:
        return {"name": "Unknown", "details": "Analysis failed.", "confidence": 0, "source": "ERROR"}

    # Extract name from the first line of AI response
    lines = raw_result.strip().split("\n")
    herb_name = lines[0].replace("*", "").strip()
    
    # Enrichment from Knowledge Base
    local_match = fetch_local_data(herb_name)
    if local_match:
        vault_text, filename = local_match
        final_details = f"### [LOCAL VAULT DATA: {filename}]\n{vault_text}\n\n### [AI ANALYSIS]\n{raw_result}"
        source = "VAULT_HYBRID"
        confidence = 98.5
    else:
        final_details = raw_result
        source = "AI_GENERATED"
        confidence = 88.0

    return {
        "name": herb_name,
        "details": final_details,
        "scientific_name": extract_scientific_name(raw_result),
        "confidence": confidence,
        "source": source,
        "matched_image_url": fetch_web_image(herb_name)
    }

# Final Alias
run_inference = process_full_analysis