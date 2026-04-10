"""
Gemini Client with OpenRouter Fallback
---------------------------------------
Shared API configuration and utility functions for LLM access.
All modules that need LLM access should import from here.

Provider priority:
  1. Gemini (google.genai SDK) — primary, free tier
  2. OpenRouter — fallback when Gemini quota is exhausted

Features:
  - Circuit breaker: after first daily-quota 429, switches to OpenRouter instantly.
  - Exponential backoff for transient errors.
  - Image (vision) support for both providers.
"""

import os
import sys
import time
import base64
import json

# --------------- Environment Setup ---------------
from dotenv import load_dotenv

_env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(os.path.abspath(_env_path))

# --------------- Gemini SDK Import ---------------
try:
    from google import genai
    from google.genai import types
    from PIL import Image
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None
    types = None
    Image = None

# --------------- OpenRouter Setup ---------------
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_AVAILABLE = bool(OPENROUTER_API_KEY)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
# Use a strong vision model on OpenRouter
OPENROUTER_MODEL = "google/gemini-2.0-flash-001"


def log(msg):
    """Log to stderr so stdout JSON stays clean for Node.js."""
    print(f"[Gemini] {msg}", file=sys.stderr, flush=True)


# --------------- Circuit Breaker ---------------
_quota_exhausted = False


def _is_daily_quota_error(error_str):
    """Check if a 429 error is a daily quota exhaustion (not just rate-limit)."""
    s = str(error_str)
    return ("429" in s and "RESOURCE_EXHAUSTED" in s and
            ("PerDay" in s or "limit: 0" in s))


def _check_circuit_breaker():
    """Returns True if Gemini calls should be skipped due to quota exhaustion."""
    return _quota_exhausted


def _trip_circuit_breaker():
    """Mark Gemini as unavailable for the rest of this process."""
    global _quota_exhausted
    if not _quota_exhausted:
        _quota_exhausted = True
        if OPENROUTER_AVAILABLE:
            log("⚠ CIRCUIT BREAKER TRIPPED — daily quota exhausted, "
                "switching to OpenRouter fallback")
        else:
            log("⚠ CIRCUIT BREAKER TRIPPED — daily quota exhausted, "
                "skipping all subsequent Gemini calls (no OpenRouter key configured)")


# --------------- Singleton Gemini Client ---------------
_client = None
MODEL_NAME = "gemini-2.0-flash"


def get_gemini_client():
    """
    Returns a configured Gemini Client instance.
    Raises RuntimeError if SDK is not installed or API key is missing.
    """
    global _client

    if _client is not None:
        return _client

    if not GEMINI_AVAILABLE:
        raise RuntimeError(
            "google-genai is not installed. Run: pip install google-genai pillow"
        )

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not found. Set it in python/.env or as an environment variable."
        )

    _client = genai.Client(api_key=api_key)
    log(f"Gemini client initialized (model: {MODEL_NAME})")
    return _client


# ===================== OPENROUTER FUNCTIONS =====================

def _openrouter_request(messages, retries=2):
    """
    Send a chat completion request to OpenRouter.
    Uses requests library (already a dependency via the OCR service).
    
    Args:
        messages: list of message dicts (OpenAI chat format)
        retries: number of retry attempts
    
    Returns:
        str: response text, or "" on failure
    """
    import requests

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://evalai.local",
        "X-Title": "EvalAI Pipeline"
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "max_tokens": 4096,
        "temperature": 0.1,
    }

    for attempt in range(retries):
        try:
            log(f"[OpenRouter] Sending request (attempt {attempt + 1}/{retries}, "
                f"model: {OPENROUTER_MODEL})")

            resp = requests.post(
                OPENROUTER_BASE_URL,
                headers=headers,
                json=payload,
                timeout=120
            )

            if resp.status_code == 200:
                data = resp.json()
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if text:
                    log(f"[OpenRouter] Response: {len(text)} chars")
                    return text.strip()
                else:
                    log("[OpenRouter] Empty response content")
            else:
                log(f"[OpenRouter] HTTP {resp.status_code}: {resp.text[:200]}")

        except Exception as e:
            log(f"[OpenRouter] Attempt {attempt + 1} failed: {e}")

        if attempt < retries - 1:
            wait_time = min(2 ** attempt * 2, 15)
            log(f"[OpenRouter] Retrying in {wait_time}s...")
            time.sleep(wait_time)

    log("[OpenRouter] All attempts failed")
    return ""


def _image_to_base64_data_url(image_path):
    """Convert an image file to a base64 data URL for OpenRouter vision."""
    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.png': 'image/png', '.gif': 'image/gif',
        '.webp': 'image/webp', '.bmp': 'image/bmp'
    }
    mime = mime_map.get(ext, 'image/jpeg')

    with open(image_path, 'rb') as f:
        img_bytes = f.read()

    b64 = base64.b64encode(img_bytes).decode('utf-8')
    return f"data:{mime};base64,{b64}"


def _openrouter_analyze_image(image_path, prompt, retries=2):
    """
    Send an image + text prompt to OpenRouter (vision model).
    """
    if not OPENROUTER_AVAILABLE:
        return ""

    try:
        data_url = _image_to_base64_data_url(image_path)
    except Exception as e:
        log(f"[OpenRouter] Failed to encode image {image_path}: {e}")
        return ""

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": data_url}
                }
            ]
        }
    ]

    return _openrouter_request(messages, retries=retries)


def _openrouter_analyze_text(prompt, retries=2):
    """
    Send a text-only prompt to OpenRouter.
    """
    if not OPENROUTER_AVAILABLE:
        return ""

    messages = [
        {"role": "user", "content": prompt}
    ]

    return _openrouter_request(messages, retries=retries)


# ===================== PUBLIC API =====================
# These functions are imported by all other modules.
# They try Gemini first, fall back to OpenRouter if circuit breaker is tripped.

def gemini_analyze_image(image_path, prompt, retries=3, timeout=60):
    """
    Send an image + text prompt to an LLM and return the text response.
    
    Provider cascade:
      1. Gemini (if quota available)
      2. OpenRouter (if Gemini quota exhausted)
    """
    # If circuit breaker is tripped, go straight to OpenRouter
    if _check_circuit_breaker():
        if OPENROUTER_AVAILABLE:
            return _openrouter_analyze_image(image_path, prompt, retries=retries)
        return ""

    # Try Gemini first
    try:
        client = get_gemini_client()
    except RuntimeError as e:
        log(f"Cannot initialize Gemini: {e}")
        # Fall back to OpenRouter
        if OPENROUTER_AVAILABLE:
            log("Falling back to OpenRouter (Gemini unavailable)")
            return _openrouter_analyze_image(image_path, prompt, retries=retries)
        return ""

    # Load the image via PIL
    try:
        img = Image.open(image_path)
    except Exception as e:
        log(f"Failed to open image {image_path}: {e}")
        return ""

    for attempt in range(retries):
        try:
            log(f"Sending image to Gemini (attempt {attempt + 1}/{retries}): {os.path.basename(image_path)}")
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=[prompt, img]
            )

            # Extract text from response
            if response and response.text:
                text = response.text.strip()
                log(f"Gemini response: {len(text)} chars")
                return text
            else:
                log("Gemini returned empty response")

        except Exception as e:
            error_str = str(e)
            log(f"Gemini attempt {attempt + 1} failed: {e}")

            # Check for daily quota exhaustion → trip circuit breaker
            if _is_daily_quota_error(error_str):
                _trip_circuit_breaker()
                # Fall back to OpenRouter
                if OPENROUTER_AVAILABLE:
                    return _openrouter_analyze_image(image_path, prompt, retries=retries)
                return ""

            if attempt < retries - 1:
                wait_time = min(2 ** attempt * 2, 30)
                log(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)

    # All Gemini attempts failed — try OpenRouter as final fallback
    if OPENROUTER_AVAILABLE:
        log("All Gemini attempts failed, trying OpenRouter...")
        return _openrouter_analyze_image(image_path, prompt, retries=2)

    log("All Gemini attempts failed, returning empty string")
    return ""


def gemini_analyze_text(prompt, retries=3):
    """
    Send a text-only prompt to an LLM and return the text response.
    
    Provider cascade:
      1. Gemini (if quota available)
      2. OpenRouter (if Gemini quota exhausted)
    """
    # If circuit breaker is tripped, go straight to OpenRouter
    if _check_circuit_breaker():
        if OPENROUTER_AVAILABLE:
            return _openrouter_analyze_text(prompt, retries=retries)
        return ""

    # Try Gemini first
    try:
        client = get_gemini_client()
    except RuntimeError as e:
        log(f"Cannot initialize Gemini: {e}")
        if OPENROUTER_AVAILABLE:
            log("Falling back to OpenRouter (Gemini unavailable)")
            return _openrouter_analyze_text(prompt, retries=retries)
        return ""

    for attempt in range(retries):
        try:
            log(f"Sending text prompt to Gemini (attempt {attempt + 1}/{retries})")
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt
            )

            if response and response.text:
                text = response.text.strip()
                log(f"Gemini response: {len(text)} chars")
                return text
            else:
                log("Gemini returned empty response")

        except Exception as e:
            error_str = str(e)
            log(f"Gemini text attempt {attempt + 1} failed: {e}")

            # Check for daily quota exhaustion → trip circuit breaker
            if _is_daily_quota_error(error_str):
                _trip_circuit_breaker()
                if OPENROUTER_AVAILABLE:
                    return _openrouter_analyze_text(prompt, retries=retries)
                return ""

            if attempt < retries - 1:
                wait_time = min(2 ** attempt * 2, 30)
                log(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)

    # All Gemini attempts failed — try OpenRouter as final fallback
    if OPENROUTER_AVAILABLE:
        log("All Gemini text attempts failed, trying OpenRouter...")
        return _openrouter_analyze_text(prompt, retries=2)

    log("All Gemini text attempts failed")
    return ""


def ai_correct_ocr_text(raw_text):
    """
    Passes raw OCR text through an LLM to correct semantic/spelling errors
    (e.g., 'machi' -> 'machine', 'Am (9' -> 'Ans (a)') while NOT hallucinating new
    content or fundamentally changing sentence structure.
    """
    if not raw_text or not raw_text.strip():
        return raw_text

    prompt = (
        "You are an AI proofreader specifically fixing raw OCR errors from a student's answer sheet. "
        "Your ONLY job is to correct misspellings, complete broken words resulting from bad image scans, "
        "and fix garbled question markers (e.g. changing something like 'Am (9' heavily into 'Ans (a)').\n\n"
        "CRITICAL RULES:\n"
        "1. DO NOT add any new information, concepts, or sentences that the student did not write.\n"
        "2. DO NOT rewrite the student's answer to sound perfectly grammatical—preserve their original phrasing, just fix broken spelling.\n"
        "3. Preserve all explicit markers (like Q1, Ans, (a), (b)) as exactly written.\n"
        "4. ABSOLUTELY DO NOT MODIFY LINE BREAKS. If a question marker like 'Q1' or 'Ans' appears at the start of a line, IT MUST STILL APPEAR AT THE START OF A NEW LINE AFTER CORRECTION.\n"
        "5. **OUTPUT ONLY THE CORRECTED STUDENT TEXT**. Do not start with 'Here is the corrected text', do not use markdown blocks, and do not add any conversational filler. Your output must be nothing but the text of the exam paper.\n\n"
        "RAW OCR TEXT TO CORRECT:\n"
        f"{raw_text}"
    )

    log("Sending raw OCR text for AI semantic correction...")
    corrected = gemini_analyze_text(prompt, retries=2)
    
    if corrected:
        # Strip potential markdown code blocks that LLMs sometimes add despite instructions
        cleaned = corrected.strip()
        if cleaned.startswith("```"):
            import re
            cleaned = re.sub(r'^```[a-z]*\s*\n?', '', cleaned)
            cleaned = re.sub(r'\n?```\s*$', '', cleaned)
            
        # Strip conversational filler if the AI ignores rule 4
        if cleaned.lower().startswith("here is the"):
            lines = cleaned.split('\n')
            if len(lines) > 1:
                cleaned = '\n'.join(lines[1:]).strip()
        
        return cleaned

    log("AI correction returned empty, falling back to raw OCR.")
    return raw_text
