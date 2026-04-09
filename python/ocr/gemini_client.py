"""
Gemini Client
-------------
Shared Gemini API configuration and utility functions.
All modules that need Gemini access should import from here.

Uses the new google.genai SDK (replaces deprecated google.generativeai).
Model: gemini-2.0-flash (fast, cost-efficient, supports vision).

Features:
  - Circuit breaker: after first daily-quota 429, skips all subsequent calls instantly.
  - Exponential backoff for transient errors.
"""

import os
import sys
import time

# --------------- Environment Setup ---------------
# Load .env from the python/ directory (parent of ocr/)
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


def log(msg):
    """Log to stderr so stdout JSON stays clean for Node.js."""
    print(f"[Gemini] {msg}", file=sys.stderr, flush=True)


# --------------- Circuit Breaker ---------------
# Once we detect a daily-quota-exhausted 429, stop wasting time on retries.
_quota_exhausted = False


def _is_daily_quota_error(error_str):
    """Check if a 429 error is a daily quota exhaustion (not just rate-limit)."""
    s = str(error_str)
    return ("429" in s and "RESOURCE_EXHAUSTED" in s and
            ("PerDay" in s or "limit: 0" in s))


def _check_circuit_breaker():
    """Returns True if Gemini calls should be skipped due to quota exhaustion."""
    if _quota_exhausted:
        return True
    return False


def _trip_circuit_breaker():
    """Mark Gemini as unavailable for the rest of this process."""
    global _quota_exhausted
    if not _quota_exhausted:
        _quota_exhausted = True
        log("⚠ CIRCUIT BREAKER TRIPPED — daily quota exhausted, skipping all subsequent Gemini calls")


# --------------- Singleton Client ---------------
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


def gemini_analyze_image(image_path, prompt, retries=3, timeout=60):
    """
    Send an image + text prompt to Gemini and return the text response.

    Features circuit breaker: if daily quota is exhausted, returns "" instantly
    without making any API calls (saving minutes on multi-page PDFs).
    """
    # Circuit breaker check
    if _check_circuit_breaker():
        return ""

    try:
        client = get_gemini_client()
    except RuntimeError as e:
        log(f"Cannot initialize Gemini: {e}")
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
                return ""

            if attempt < retries - 1:
                wait_time = min(2 ** attempt * 2, 30)
                log(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)

    log("All Gemini attempts failed, returning empty string")
    return ""


def gemini_analyze_text(prompt, retries=3):
    """
    Send a text-only prompt to Gemini and return the text response.
    Used for evaluation tasks that don't require images.
    """
    # Circuit breaker check
    if _check_circuit_breaker():
        return ""

    try:
        client = get_gemini_client()
    except RuntimeError as e:
        log(f"Cannot initialize Gemini: {e}")
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
                return ""

            if attempt < retries - 1:
                wait_time = min(2 ** attempt * 2, 30)
                log(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)

    log("All Gemini text attempts failed")
    return ""
