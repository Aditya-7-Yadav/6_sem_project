"""
Diagram Evaluator
------------------
Evaluates student diagrams against model answer diagram descriptions
using Gemini Vision API.

Key features:
  - Concept-level comparison (not pixel-level)
  - Handles different drawing styles for same concept
  - Structured evaluation: components, connections, labels
  - Partial marking for incomplete/unclear diagrams
  - Fallback strategies when Gemini is unavailable

Usage:
    from ocr.diagram_evaluator import evaluate_diagram
    result = evaluate_diagram(
        image_path="/path/to/student_page.jpg",
        model_diagram_data={
            "description": "Process state diagram with 5 states",
            "elements": ["New", "Ready", "Running", "Waiting", "Terminated"],
            "connections": [["New", "Ready"], ["Ready", "Running"], ...]
        },
        model_text="A process state diagram shows...",
        max_marks=5
    )
"""

import os
import sys
import json
import re

# --------------- Path Setup ---------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_DIR = os.path.dirname(SCRIPT_DIR)
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)

# --------------- Imports ---------------
from ocr.gemini_client import gemini_analyze_image, gemini_analyze_text, log, GEMINI_AVAILABLE


def log_diag(msg):
    """Log with module prefix."""
    print(f"[DiagramEvaluator] {msg}", file=sys.stderr, flush=True)


# ===================== EVALUATION PROMPTS =====================

DIAGRAM_STRUCTURED_EVAL_PROMPT = """You are evaluating a student's diagram from an exam answer sheet.

**Image:** (attached — the student's handwritten/drawn diagram)

**Expected Diagram (from model answer):**
Description: {diagram_description}
Required Elements/Components: {diagram_elements}
Required Connections/Relationships: {diagram_connections}

**Model Answer Text (for context):**
{model_text}

**Maximum Marks:** {max_marks}

**Evaluation Criteria (evaluate each independently, then combine):**
1. STRUCTURAL CORRECTNESS (30%): Are the correct components/elements present?
   - List which required elements are present vs missing
2. CONNECTIONS/RELATIONSHIPS (25%): Are components correctly connected/related?
   - List which connections are correct vs missing vs wrong
3. LABELING (20%): Are components properly and correctly labeled?
   - Note any missing or incorrect labels
4. CONCEPTUAL ACCURACY (15%): Does the diagram convey the correct concept?
   - Even if drawn differently, does it show the right idea?
5. COMPLETENESS & NEATNESS (10%): Is the diagram complete and readable?

**IMPORTANT:** Different drawing styles are ACCEPTABLE. 
A student may draw the same concept differently from the model answer — 
if the concept is correct, they should get full marks for that criterion.

Return ONLY a valid JSON object:
{{
    "marks_awarded": <number between 0 and {max_marks}>,
    "max_marks": {max_marks},
    "structural_score": <0-100>,
    "connection_score": <0-100>,
    "labeling_score": <0-100>,
    "conceptual_score": <0-100>,
    "completeness_score": <0-100>,
    "elements_found": ["element1", "element2"],
    "elements_missing": ["element3"],
    "connections_correct": [["from1", "to1"]],
    "connections_missing": [["from2", "to2"]],
    "reason": "<brief explanation of marks, 2-3 sentences>"
}}
"""

DIAGRAM_SIMPLE_EVAL_PROMPT = """You are evaluating a student's diagram from an exam answer sheet.

**Image:** (attached — the student's handwritten/drawn diagram)

**Expected Content (from model answer):**
{model_text}

**Maximum Marks:** {max_marks}

Evaluate the student's diagram for:
1. Correct components/elements
2. Correct connections/relationships
3. Proper labeling
4. Conceptual accuracy (different drawing style is OK if concept is correct)
5. Completeness

Return ONLY a valid JSON object:
{{
    "marks_awarded": <number between 0 and {max_marks}>,
    "max_marks": {max_marks},
    "reason": "<brief explanation, 1-2 sentences>"
}}
"""


# ===================== MAIN EVALUATION FUNCTION =====================

def evaluate_diagram(image_path, model_diagram_data=None, model_text="",
                     max_marks=5, question_number="?"):
    """
    Evaluate a student's diagram against the model answer.

    Args:
        image_path (str): Path to the page image containing the diagram.
        model_diagram_data (dict): Structured diagram description from model answer.
            Expected: {"description": str, "elements": list, "connections": list}
        model_text (str): Model answer text for context.
        max_marks (float): Maximum marks for the diagram component.
        question_number (str): Question number for logging.

    Returns:
        dict: {
            "marks_awarded": float,
            "max_marks": float,
            "diagram_score": float (0-1),
            "reason": str,
            "details": dict (breakdown scores),
            "evaluation_type": "structured" | "simple" | "fallback"
        }
    """
    max_marks = float(max_marks)

    # Default result on failure
    default_result = {
        "marks_awarded": 0,
        "max_marks": max_marks,
        "diagram_score": 0.0,
        "reason": "Diagram evaluation failed",
        "details": {},
        "evaluation_type": "failed"
    }

    # Check if image exists
    if not image_path or not os.path.exists(image_path):
        log_diag(f"Q{question_number}: No image available for diagram evaluation — awarding partial marks")
        # Award partial marks based on expected diagram complexity
        return _fallback_partial_marks(max_marks, question_number)

    # Check if Gemini is available
    if not GEMINI_AVAILABLE:
        log_diag(f"Q{question_number}: Gemini not available — awarding partial marks")
        return _fallback_partial_marks(max_marks, question_number)

    log_diag(f"Q{question_number}: Evaluating diagram (max_marks={max_marks})")

    # Choose evaluation strategy based on available model data
    if model_diagram_data and model_diagram_data.get("elements"):
        result = _evaluate_structured(
            image_path, model_diagram_data, model_text,
            max_marks, question_number
        )
    else:
        result = _evaluate_simple(
            image_path, model_text, max_marks, question_number
        )

    if result:
        return result

    # If evaluation failed, try simple approach
    if model_diagram_data:
        result = _evaluate_simple(
            image_path, model_text, max_marks, question_number
        )
        if result:
            return result

    # Last resort: partial marks
    return _fallback_partial_marks(max_marks, question_number)


# ===================== STRUCTURED EVALUATION =====================

def _evaluate_structured(image_path, diagram_data, model_text, max_marks, question_number):
    """
    Evaluate using structured diagram data (elements, connections).
    This is the most accurate evaluation mode.
    """
    elements_str = json.dumps(diagram_data.get("elements", []))
    connections_str = json.dumps(diagram_data.get("connections", []))
    description = diagram_data.get("description", "No description available")

    prompt = DIAGRAM_STRUCTURED_EVAL_PROMPT.format(
        diagram_description=description,
        diagram_elements=elements_str,
        diagram_connections=connections_str,
        model_text=model_text[:2000],
        max_marks=max_marks
    )

    log_diag(f"Q{question_number}: Using structured evaluation "
             f"({len(diagram_data.get('elements', []))} elements)")

    response = gemini_analyze_image(image_path, prompt)
    result = _parse_diagram_response(response, max_marks)

    if result:
        result["evaluation_type"] = "structured"
        # Compute diagram_score as normalized 0-1
        result["diagram_score"] = round(
            result["marks_awarded"] / max_marks if max_marks > 0 else 0.0, 3
        )
        log_diag(f"Q{question_number}: Structured eval → "
                 f"{result['marks_awarded']}/{max_marks} "
                 f"(score={result['diagram_score']})")
        return result

    return None


# ===================== SIMPLE EVALUATION =====================

def _evaluate_simple(image_path, model_text, max_marks, question_number):
    """
    Evaluate using only model text (no structured diagram data).
    Less accurate but always available if Gemini works.
    """
    if not model_text:
        model_text = "A diagram is expected for this answer."

    prompt = DIAGRAM_SIMPLE_EVAL_PROMPT.format(
        model_text=model_text[:3000],
        max_marks=max_marks
    )

    log_diag(f"Q{question_number}: Using simple evaluation (text-only context)")

    response = gemini_analyze_image(image_path, prompt)
    result = _parse_diagram_response(response, max_marks)

    if result:
        result["evaluation_type"] = "simple"
        result["diagram_score"] = round(
            result["marks_awarded"] / max_marks if max_marks > 0 else 0.0, 3
        )
        log_diag(f"Q{question_number}: Simple eval → "
                 f"{result['marks_awarded']}/{max_marks}")
        return result

    return None


# ===================== RESPONSE PARSING =====================

def _parse_diagram_response(response_text, max_marks):
    """
    Parse Gemini's diagram evaluation response.
    """
    if not response_text:
        return None

    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)

    try:
        parsed = json.loads(cleaned)

        marks = float(parsed.get("marks_awarded", 0))
        marks = max(0, min(marks, float(max_marks)))

        details = {}
        for key in ["structural_score", "connection_score", "labeling_score",
                     "conceptual_score", "completeness_score",
                     "elements_found", "elements_missing",
                     "connections_correct", "connections_missing"]:
            if key in parsed:
                details[key] = parsed[key]

        return {
            "marks_awarded": round(marks, 1),
            "max_marks": float(max_marks),
            "diagram_score": 0.0,  # Will be set by caller
            "reason": str(parsed.get("reason", "No reason provided")),
            "details": details,
            "evaluation_type": "unknown"  # Will be set by caller
        }

    except (json.JSONDecodeError, ValueError, TypeError) as e:
        log_diag(f"Failed to parse diagram evaluation response: {e}")

        # Try to extract marks from non-JSON response
        marks_match = re.search(
            r'marks?\s*(?:awarded|given)?\s*[:=]\s*(\d+(?:\.\d+)?)',
            response_text, re.IGNORECASE
        )
        if marks_match:
            marks = float(marks_match.group(1))
            marks = max(0, min(marks, float(max_marks)))
            return {
                "marks_awarded": round(marks, 1),
                "max_marks": float(max_marks),
                "diagram_score": 0.0,
                "reason": "Marks extracted from AI response (non-standard format)",
                "details": {},
                "evaluation_type": "unknown"
            }

        return None


# ===================== FALLBACK =====================

def _fallback_partial_marks(max_marks, question_number):
    """
    Award partial marks when evaluation cannot be performed.
    Strategy: award ~30% of marks for attempting a diagram.
    """
    partial = round(max_marks * 0.3, 1)
    log_diag(f"Q{question_number}: Fallback partial marks → {partial}/{max_marks}")

    return {
        "marks_awarded": partial,
        "max_marks": float(max_marks),
        "diagram_score": 0.3,
        "reason": "Diagram evaluation unavailable — partial marks awarded for attempt",
        "details": {},
        "evaluation_type": "fallback"
    }
