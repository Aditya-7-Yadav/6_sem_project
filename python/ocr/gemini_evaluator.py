"""
Gemini Evaluator
-----------------
AI-based answer evaluation using Google Gemini.

For each answer component, evaluates correctness against the model answer
and returns marks with reasoning. Handles different content types:
  - Text answers → content accuracy + completeness
  - Diagrams → structural + labeling correctness
  - Graphs → shape + axis correctness
  - Numericals → steps + final answer verification
  - Theorems → correctness + completeness of proof

Output per question:
{
    "question_number": "1",
    "marks_awarded": 4,
    "max_marks": 5,
    "reason": "Diagram mostly correct but labeling missing",
    "content_types_evaluated": ["text", "diagram"]
}
"""

import os
import sys
import json
import re

from .gemini_client import gemini_analyze_text, gemini_analyze_image, log


# --------------- Evaluation Prompt Templates ---------------

TEXT_EVAL_PROMPT = """You are an expert exam evaluator. Compare the student's answer with the model answer and award marks.

**Model Answer:**
{model_answer}

**Student Answer:**
{student_answer}

**Maximum Marks:** {max_marks}

**Evaluation Criteria:**
- Content accuracy and factual correctness
- Completeness of key points covered
- Clarity of explanation
- Relevant examples (if applicable)

Return ONLY a valid JSON object:
{{
    "marks_awarded": <number between 0 and {max_marks}>,
    "max_marks": {max_marks},
    "reason": "<brief explanation of marks awarded, 1-2 sentences>"
}}
"""

DIAGRAM_EVAL_PROMPT = """You are evaluating a student's diagram/figure from an exam answer sheet.

**Image:** (attached)

**Expected Diagram Description from Model Answer:**
{model_answer}

**Maximum Marks:** {max_marks}

**Evaluation Criteria for Diagrams:**
- Structural correctness (correct components/elements)
- Proper labeling of parts
- Correct connections/relationships shown
- Neatness and clarity
- Completeness (all required elements present)

Return ONLY a valid JSON object:
{{
    "marks_awarded": <number between 0 and {max_marks}>,
    "max_marks": {max_marks},
    "reason": "<brief explanation, mention specific missing/incorrect elements>"
}}
"""

NUMERICAL_EVAL_PROMPT = """You are evaluating a student's numerical/mathematical solution.

**Model Answer (Expected Solution):**
{model_answer}

**Student Answer:**
{student_answer}

**Maximum Marks:** {max_marks}

**Evaluation Criteria for Numerical Solutions:**
- Correct approach/method used
- Step-by-step solution shown
- Correct intermediate calculations
- Correct final answer
- Proper units (if applicable)

Award partial marks for correct steps even if the final answer is wrong.

Return ONLY a valid JSON object:
{{
    "marks_awarded": <number between 0 and {max_marks}>,
    "max_marks": {max_marks},
    "reason": "<brief explanation, mention if steps are correct but answer is wrong, etc.>"
}}
"""

THEOREM_EVAL_PROMPT = """You are evaluating a student's theorem/proof/derivation answer.

**Model Answer (Expected Proof):**
{model_answer}

**Student Answer:**
{student_answer}

**Maximum Marks:** {max_marks}

**Evaluation Criteria for Theorems/Proofs:**
- Correct statement of the theorem
- Logical flow of the proof
- All steps justified
- Completeness of the proof
- Correct mathematical notation

Return ONLY a valid JSON object:
{{
    "marks_awarded": <number between 0 and {max_marks}>,
    "max_marks": {max_marks},
    "reason": "<brief explanation of what's correct/missing in the proof>"
}}
"""


def evaluate_answer(student_answer, model_answer, max_marks,
                    content_types=None, image_path=None, question_number="?"):
    """
    Evaluate a student's answer against the model answer using Gemini.

    Args:
        student_answer (str): Student's extracted answer text.
        model_answer (str): The correct/expected answer.
        max_marks (int/float): Maximum marks for this question.
        content_types (list): List of content types detected (e.g., ["text", "diagram"]).
        image_path (str): Path to the page image (for diagram/graph evaluation).
        question_number (str): Question number for logging.

    Returns:
        dict: {
            "question_number": str,
            "marks_awarded": float,
            "max_marks": float,
            "reason": str,
            "content_types_evaluated": list
        }
    """
    max_marks = float(max_marks)
    content_types = content_types or ["text"]

    # Default result on complete failure
    default_result = {
        "question_number": str(question_number),
        "marks_awarded": 0,
        "max_marks": max_marks,
        "reason": "Evaluation failed — could not process answer",
        "content_types_evaluated": content_types
    }

    # If no student answer and no image, award 0
    if not student_answer and not image_path:
        default_result["reason"] = "No answer provided by student"
        return default_result

    log(f"Evaluating Q{question_number}: types={content_types}, max_marks={max_marks}")

    # Choose evaluation strategy based on content types
    if "diagram" in content_types and image_path:
        result = _evaluate_with_image(image_path, model_answer, max_marks, "diagram")
    elif "graph" in content_types and image_path:
        result = _evaluate_with_image(image_path, model_answer, max_marks, "graph")
    elif "numerical" in content_types:
        result = _evaluate_text(student_answer, model_answer, max_marks, "numerical")
    elif "theorem" in content_types:
        result = _evaluate_text(student_answer, model_answer, max_marks, "theorem")
    else:
        result = _evaluate_text(student_answer, model_answer, max_marks, "text")

    if result:
        result["question_number"] = str(question_number)
        result["content_types_evaluated"] = content_types
        log(f"Q{question_number}: {result['marks_awarded']}/{result['max_marks']} — {result['reason'][:80]}")
        return result

    return default_result


def _evaluate_text(student_answer, model_answer, max_marks, content_type="text"):
    """
    Evaluate a text-based answer using Gemini text analysis.
    """
    # Select the right prompt template
    if content_type == "numerical":
        prompt = NUMERICAL_EVAL_PROMPT.format(
            student_answer=student_answer, model_answer=model_answer, max_marks=max_marks
        )
    elif content_type == "theorem":
        prompt = THEOREM_EVAL_PROMPT.format(
            student_answer=student_answer, model_answer=model_answer, max_marks=max_marks
        )
    else:
        prompt = TEXT_EVAL_PROMPT.format(
            student_answer=student_answer, model_answer=model_answer, max_marks=max_marks
        )

    response = gemini_analyze_text(prompt)
    return _parse_eval_response(response, max_marks)


def _evaluate_with_image(image_path, model_answer, max_marks, content_type="diagram"):
    """
    Evaluate visual content (diagram/graph) by sending the image to Gemini.
    """
    prompt = DIAGRAM_EVAL_PROMPT.format(
        model_answer=model_answer, max_marks=max_marks
    )

    response = gemini_analyze_image(image_path, prompt)
    return _parse_eval_response(response, max_marks)


def _parse_eval_response(response_text, max_marks):
    """
    Parse Gemini's evaluation response into marks + reason.
    """
    if not response_text:
        return None

    # Strip markdown code blocks
    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)

    try:
        parsed = json.loads(cleaned)

        marks = float(parsed.get("marks_awarded", 0))
        # Ensure marks are within valid range
        marks = max(0, min(marks, float(max_marks)))

        return {
            "marks_awarded": round(marks, 1),
            "max_marks": float(max_marks),
            "reason": str(parsed.get("reason", "No reason provided"))
        }

    except (json.JSONDecodeError, ValueError, TypeError) as e:
        log(f"Failed to parse evaluation response: {e}")
        log(f"Raw response: {response_text[:300]}")

        # Attempt to extract marks from non-JSON response
        return _extract_marks_fallback(response_text, max_marks)


def _extract_marks_fallback(text, max_marks):
    """
    Fallback: try to extract marks from Gemini's response even if it's not valid JSON.
    """
    marks_match = re.search(r'marks?\s*(?:awarded|given)?\s*[:=]\s*(\d+(?:\.\d+)?)', text, re.IGNORECASE)

    if marks_match:
        marks = float(marks_match.group(1))
        marks = max(0, min(marks, float(max_marks)))
        return {
            "marks_awarded": round(marks, 1),
            "max_marks": float(max_marks),
            "reason": "Marks extracted from AI response (non-standard format)"
        }

    return None


def evaluate_batch(questions, image_paths=None):
    """
    Evaluate a batch of questions.

    Args:
        questions (list): List of dicts with keys:
            - question_number, student_answer, model_answer, max_marks, content_types
        image_paths (dict): Optional mapping of page_number -> image_path

    Returns:
        list: List of evaluation results.
    """
    import time

    results = []
    image_paths = image_paths or {}

    for q in questions:
        qnum = q.get("question_number", "?")
        img_path = image_paths.get(str(qnum))

        result = evaluate_answer(
            student_answer=q.get("student_answer", ""),
            model_answer=q.get("model_answer", ""),
            max_marks=q.get("max_marks", 5),
            content_types=q.get("content_types", ["text"]),
            image_path=img_path,
            question_number=qnum
        )
        results.append(result)

        # Rate limiting — Gemini free tier has limits
        time.sleep(1)

    return results
