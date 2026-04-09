"""
Gemini First Page Extractor
----------------------------
Extracts structured student information from the first page of an answer sheet
using Google Gemini vision analysis.

Instead of skipping the first page (as the old pipeline did), this module
sends the first page image to Gemini and extracts:
  - Name
  - Roll Number
  - Exam Date
  - Branch
  - Subject / Paper Code

Output format:
{
    "name": "...",
    "roll_number": "...",
    "exam_date": "...",
    "branch": "...",
    "paper_code": ""
}
"""

import os
import sys
import json
import re

# Import shared Gemini client from the same package
from .gemini_client import gemini_analyze_image, log


# --------------- Prompt Template ---------------
FIRST_PAGE_PROMPT = """You are analyzing the first page (cover page) of a student's handwritten answer sheet from an exam.

Extract the following student information from this image. Look for handwritten or printed fields like Name, Roll Number, Enrollment Number, Registration Number, Date, Branch, Department, Subject, Paper Code, Course Code, etc.

Return ONLY a valid JSON object with these exact keys (use empty string if a field is not found):

{
    "name": "",
    "roll_number": "",
    "exam_date": "",
    "branch": "",
    "paper_code": ""
}

Rules:
- "roll_number" can be any student ID: roll number, enrollment number, registration number, PRN, etc.
- "exam_date" should be in the format found on the sheet (DD/MM/YYYY or similar)
- "branch" is the department or stream (e.g., CSE, ECE, Mechanical)
- "paper_code" is the subject code or course code
- If a field has multiple possible values, pick the most prominent one
- Return ONLY the JSON, no explanations or markdown formatting
"""


def extract_student_info(image_path):
    """
    Extract structured student information from the first page image.

    Args:
        image_path (str): Path to the first page image file.

    Returns:
        dict: Student info with keys: name, roll_number, exam_date, branch, paper_code.
              All values default to empty string if extraction fails.
    """
    # Default empty result
    empty_result = {
        "name": "",
        "roll_number": "",
        "exam_date": "",
        "branch": "",
        "paper_code": ""
    }

    if not os.path.exists(image_path):
        log(f"First page image not found: {image_path}")
        return empty_result

    log(f"Extracting student info from first page: {os.path.basename(image_path)}")

    # Send to Gemini
    response_text = gemini_analyze_image(image_path, FIRST_PAGE_PROMPT)

    if not response_text:
        log("Gemini returned no response for first page — returning empty info")
        return empty_result

    # Parse the JSON from Gemini's response
    return _parse_student_info_response(response_text)


def _parse_student_info_response(response_text):
    """
    Parse Gemini's response text into a structured student info dict.
    Handles cases where Gemini wraps JSON in markdown code blocks.
    """
    empty_result = {
        "name": "",
        "roll_number": "",
        "exam_date": "",
        "branch": "",
        "paper_code": ""
    }

    # Strip markdown code block wrappers if present (```json ... ```)
    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        # Remove opening ``` (possibly with language tag)
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
        # Remove closing ```
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)

    try:
        parsed = json.loads(cleaned)

        # Validate and extract only expected keys
        result = {}
        for key in empty_result.keys():
            value = parsed.get(key, "")
            # Ensure it's a string
            result[key] = str(value).strip() if value else ""

        log(f"Student info extracted: name='{result['name']}', "
            f"roll='{result['roll_number']}', branch='{result['branch']}'")

        return result

    except json.JSONDecodeError as e:
        log(f"Failed to parse Gemini response as JSON: {e}")
        log(f"Raw response (first 300 chars): {response_text[:300]}")

        # Attempt manual extraction as fallback
        return _manual_extract_fallback(response_text)


def _manual_extract_fallback(text):
    """
    Fallback: try to extract student info using regex patterns
    when Gemini doesn't return valid JSON.
    """
    log("Attempting manual regex extraction from Gemini response...")

    result = {
        "name": "",
        "roll_number": "",
        "exam_date": "",
        "branch": "",
        "paper_code": ""
    }

    # Try to find name
    name_match = re.search(r'(?:name|student)\s*[:=]\s*["\']?([^"\'\n,}{]+)', text, re.IGNORECASE)
    if name_match:
        result["name"] = name_match.group(1).strip()

    # Try to find roll number
    roll_match = re.search(
        r'(?:roll|enrollment|reg(?:istration)?|prn)\s*(?:no|number|num)?\s*[:=]\s*["\']?([^"\'\n,}{]+)',
        text, re.IGNORECASE
    )
    if roll_match:
        result["roll_number"] = roll_match.group(1).strip()

    # Try to find date
    date_match = re.search(
        r'(?:date|exam.?date)\s*[:=]\s*["\']?([^"\'\n,}{]+)',
        text, re.IGNORECASE
    )
    if date_match:
        result["exam_date"] = date_match.group(1).strip()

    # Try to find branch
    branch_match = re.search(
        r'(?:branch|dept|department|stream)\s*[:=]\s*["\']?([^"\'\n,}{]+)',
        text, re.IGNORECASE
    )
    if branch_match:
        result["branch"] = branch_match.group(1).strip()

    # Try to find paper code
    paper_match = re.search(
        r'(?:paper|subject|course)\s*(?:code|no)?\s*[:=]\s*["\']?([^"\'\n,}{]+)',
        text, re.IGNORECASE
    )
    if paper_match:
        result["paper_code"] = paper_match.group(1).strip()

    extracted_count = sum(1 for v in result.values() if v)
    log(f"Manual extraction found {extracted_count}/5 fields")

    return result
