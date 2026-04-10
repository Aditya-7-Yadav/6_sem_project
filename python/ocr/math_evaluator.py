"""
Math Evaluator
---------------
Evaluates mathematical and numerical student answers using:
  1. SymPy symbolic comparison (expression equivalence)
  2. Step validation (are intermediate steps correct?)
  3. Final answer extraction and comparison
  4. Fallback to Gemini numerical evaluation

Handles:
  - Equations and formulas
  - Step-by-step solutions
  - Final answer verification
  - Different representations of same expression (e.g., x+1 vs 1+x)

Usage:
    from ocr.math_evaluator import evaluate_math
    result = evaluate_math(
        student_answer="x = (-b ± √(b²-4ac)) / 2a = (3 ± √9-8) / 2 = 2 or 1",
        model_answer="Using quadratic formula: x = (-b ± √(b²-4ac)) / 2a...",
        model_expressions=["x = (-b ± √(b²-4ac)) / 2a", "x = 2", "x = 1"],
        max_marks=5
    )
"""

import os
import sys
import re

# --------------- Path Setup ---------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_DIR = os.path.dirname(SCRIPT_DIR)
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)

# --------------- Imports ---------------
from ocr.gemini_client import gemini_analyze_text, log, GEMINI_AVAILABLE

# Try importing sympy
try:
    import sympy
    from sympy.parsing.sympy_parser import parse_expr, standard_transformations
    SYMPY_AVAILABLE = True
except ImportError:
    SYMPY_AVAILABLE = False
    sympy = None


def log_math(msg):
    """Log with module prefix."""
    print(f"[MathEvaluator] {msg}", file=sys.stderr, flush=True)


# ===================== EXPRESSION PARSING =====================

def _clean_expression(expr_str):
    """
    Clean a mathematical expression string for SymPy parsing.
    Handles common OCR artifacts and notation variations.
    """
    if not expr_str:
        return ""

    s = str(expr_str).strip()

    # Remove common text surrounding expressions
    s = re.sub(r'^(?:therefore|hence|so|thus|ans(?:wer)?)\s*[:=]?\s*',
               '', s, flags=re.IGNORECASE)

    # Normalize common symbols
    s = s.replace('×', '*').replace('÷', '/')
    s = s.replace('−', '-').replace('–', '-')
    s = s.replace('^', '**')
    s = s.replace('√', 'sqrt')

    # Handle implied multiplication: "2x" → "2*x"
    s = re.sub(r'(\d)([a-zA-Z])', r'\1*\2', s)

    # Remove units and trailing text
    s = re.sub(r'\s*(cm|m|kg|s|sec|min|hr|units?|meters?|seconds?)\s*$',
               '', s, flags=re.IGNORECASE)

    return s.strip()


def _parse_sympy_expr(expr_str):
    """
    Attempt to parse a string as a SymPy expression.
    Returns (expression, True) on success, (None, False) on failure.
    """
    if not SYMPY_AVAILABLE or not expr_str:
        return None, False

    cleaned = _clean_expression(expr_str)
    if not cleaned:
        return None, False

    # Try direct parsing
    try:
        expr = parse_expr(cleaned, transformations=standard_transformations)
        return expr, True
    except Exception:
        pass

    # Try simplifying first (handle things like "2+3" → 5)
    try:
        expr = sympy.sympify(cleaned)
        return expr, True
    except Exception:
        pass

    return None, False


# ===================== NUMERICAL EXTRACTION =====================

def _extract_numbers(text):
    """
    Extract all numerical values from text.
    Returns list of floats.
    """
    if not text:
        return []

    # Match integers, decimals, fractions
    patterns = [
        r'-?\d+\.\d+',       # decimals
        r'-?\d+/\d+',        # fractions
        r'-?\d+',            # integers
    ]

    numbers = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            try:
                val = match.group()
                if '/' in val:
                    parts = val.split('/')
                    numbers.append(float(parts[0]) / float(parts[1]))
                else:
                    numbers.append(float(val))
            except (ValueError, ZeroDivisionError):
                pass

    return numbers


def _extract_final_answer(text):
    """
    Extract what appears to be the final answer from a solution.
    Looks for patterns like "= 5", "Answer: 42", "therefore x = 3"
    """
    if not text:
        return None

    # Try patterns that indicate a final answer
    patterns = [
        r'(?:therefore|hence|so|thus|answer|ans|result)\s*[:=]?\s*(\S+(?:\s*[=]\s*\S+)?)',
        r'(?:^|\n)\s*=\s*(\S+)\s*$',  # standalone "= value" at end
        r'(\S+)\s*$',  # last value in text
    ]

    for pattern in patterns:
        match = re.search(pattern, text.strip(), re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()

    return None


# ===================== COMPARISON FUNCTIONS =====================

def _compare_expressions(student_expr_str, model_expr_str):
    """
    Compare two mathematical expressions symbolically.
    Returns similarity score (0-1).
    """
    if not SYMPY_AVAILABLE:
        return None

    student_expr, student_ok = _parse_sympy_expr(student_expr_str)
    model_expr, model_ok = _parse_sympy_expr(model_expr_str)

    if not student_ok or not model_ok:
        return None

    try:
        # Check if expressions are mathematically equivalent
        diff = sympy.simplify(student_expr - model_expr)
        if diff == 0:
            return 1.0

        # Check if they're equal after expansion
        if sympy.expand(student_expr) == sympy.expand(model_expr):
            return 1.0

        # Check ratio (handles proportional equivalence)
        if model_expr != 0:
            ratio = sympy.simplify(student_expr / model_expr)
            if ratio == 1:
                return 1.0

        # Partial similarity — check if common subexpressions exist
        return 0.3  # Different but parseable expressions

    except Exception:
        return None


def _compare_numerical_values(student_text, model_text, tolerance=0.01):
    """
    Compare numerical values in student and model answers.
    Returns score based on how many model values the student got correct.
    """
    student_nums = _extract_numbers(student_text)
    model_nums = _extract_numbers(model_text)

    if not model_nums:
        return None

    if not student_nums:
        return 0.0

    # Count how many model numbers appear in student answer (within tolerance)
    matched = 0
    for model_val in model_nums:
        for student_val in student_nums:
            if abs(model_val) < 1e-10:
                if abs(student_val) < 1e-10:
                    matched += 1
                    break
            elif abs((student_val - model_val) / model_val) <= tolerance:
                matched += 1
                break

    return matched / len(model_nums)


def _compare_final_answers(student_text, model_text):
    """
    Compare final answers specifically.
    First tries symbolic, then numerical.
    """
    student_final = _extract_final_answer(student_text)
    model_final = _extract_final_answer(model_text)

    if not student_final or not model_final:
        return None

    # Try symbolic comparison
    sym_result = _compare_expressions(student_final, model_final)
    if sym_result is not None:
        return sym_result

    # Try numerical comparison
    try:
        s_val = float(re.sub(r'[^0-9.\-/]', '', student_final))
        m_val = float(re.sub(r'[^0-9.\-/]', '', model_final))
        if abs(m_val) < 1e-10:
            return 1.0 if abs(s_val) < 1e-10 else 0.0
        return 1.0 if abs((s_val - m_val) / m_val) <= 0.01 else 0.0
    except (ValueError, ZeroDivisionError):
        pass

    # String comparison as last resort
    student_clean = re.sub(r'\s+', '', student_final.lower())
    model_clean = re.sub(r'\s+', '', model_final.lower())
    return 1.0 if student_clean == model_clean else 0.0


# ===================== STEP VALIDATION =====================

def _validate_steps(student_text, model_text, model_expressions=None):
    """
    Validate that the student showed correct intermediate steps.
    Returns a score based on step coverage.
    """
    if not model_expressions:
        # Extract expressions from model text
        expressions = re.findall(
            r'(?:^|\s)([^=\n]+\s*=\s*[^=\n]+)(?:\s|$)',
            model_text
        )
        model_expressions = [e.strip() for e in expressions if len(e.strip()) > 3]

    if not model_expressions:
        return None

    # Check how many model expressions appear (symbolically or textually) in student
    step_matches = 0
    for expr in model_expressions:
        # Symbolic check
        if SYMPY_AVAILABLE:
            sym_score = _compare_expressions(expr, student_text)
            if sym_score and sym_score > 0.5:
                step_matches += 1
                continue

        # Text-based check (is the expression substring present?)
        expr_clean = re.sub(r'\s+', '', expr.lower())
        student_clean = re.sub(r'\s+', '', student_text.lower())
        if expr_clean in student_clean:
            step_matches += 1

    return step_matches / len(model_expressions) if model_expressions else 0.0


# ===================== GEMINI FALLBACK =====================

def _gemini_evaluate_math(student_answer, model_answer, max_marks):
    """
    Fallback: Use Gemini to evaluate mathematical answer.
    """
    if not GEMINI_AVAILABLE:
        return None

    prompt = f"""You are evaluating a student's mathematical/numerical solution.

**Model Answer (Expected Solution):**
{model_answer}

**Student Answer:**
{student_answer}

**Maximum Marks:** {max_marks}

**Evaluation Criteria:**
- Correct approach/method used (25%)
- Step-by-step solution shown (25%)
- Correct intermediate calculations (25%)
- Correct final answer (25%)

Award partial marks for correct steps even if the final answer is wrong.
A correct final answer with no steps shown should get ~60% marks.

Return ONLY a valid JSON object:
{{
    "marks_awarded": <number between 0 and {max_marks}>,
    "max_marks": {max_marks},
    "approach_correct": true/false,
    "steps_shown": true/false,
    "final_answer_correct": true/false,
    "reason": "<brief explanation>"
}}
"""

    response = gemini_analyze_text(prompt)
    if not response:
        return None

    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)

    try:
        parsed = json.loads(cleaned)
        marks = float(parsed.get("marks_awarded", 0))
        marks = max(0, min(marks, float(max_marks)))

        return {
            "marks_awarded": round(marks, 1),
            "max_marks": float(max_marks),
            "math_score": round(marks / max_marks if max_marks > 0 else 0.0, 3),
            "reason": str(parsed.get("reason", "")),
            "details": {
                "approach_correct": parsed.get("approach_correct"),
                "steps_shown": parsed.get("steps_shown"),
                "final_answer_correct": parsed.get("final_answer_correct"),
            },
            "evaluation_type": "gemini"
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


# Need json for Gemini fallback
import json


# ===================== MAIN EVALUATION FUNCTION =====================

def evaluate_math(student_answer, model_answer, model_expressions=None,
                  max_marks=5, question_number="?"):
    """
    Evaluate a mathematical/numerical student answer.

    Args:
        student_answer (str): Student's extracted answer text.
        model_answer (str): The correct/expected answer.
        model_expressions (list): Expected mathematical expressions.
        max_marks (float): Maximum marks for this question.
        question_number (str): Question number for logging.

    Returns:
        dict: {
            "marks_awarded": float,
            "max_marks": float,
            "math_score": float (0-1),
            "reason": str,
            "details": dict,
            "evaluation_type": str
        }
    """
    max_marks = float(max_marks)

    default_result = {
        "marks_awarded": 0,
        "max_marks": max_marks,
        "math_score": 0.0,
        "reason": "Math evaluation failed",
        "details": {},
        "evaluation_type": "failed"
    }

    if not student_answer or not student_answer.strip():
        default_result["reason"] = "No answer provided"
        return default_result

    log_math(f"Q{question_number}: Evaluating math answer "
             f"(sympy={SYMPY_AVAILABLE}, max_marks={max_marks})")

    # Strategy 1: SymPy-based evaluation
    if SYMPY_AVAILABLE:
        sympy_result = _sympy_evaluate(
            student_answer, model_answer, model_expressions, max_marks
        )
        if sympy_result:
            log_math(f"Q{question_number}: SymPy eval → "
                     f"{sympy_result['marks_awarded']}/{max_marks}")
            return sympy_result

    # Strategy 2: Numerical comparison
    num_result = _numerical_evaluate(
        student_answer, model_answer, model_expressions, max_marks
    )
    if num_result:
        log_math(f"Q{question_number}: Numerical eval → "
                 f"{num_result['marks_awarded']}/{max_marks}")
        return num_result

    # Strategy 3: Gemini fallback
    gemini_result = _gemini_evaluate_math(student_answer, model_answer, max_marks)
    if gemini_result:
        log_math(f"Q{question_number}: Gemini eval → "
                 f"{gemini_result['marks_awarded']}/{max_marks}")
        return gemini_result

    # Last resort: award minimal marks for showing work
    if len(student_answer.strip()) > 20:
        partial = round(max_marks * 0.2, 1)
        log_math(f"Q{question_number}: Fallback partial marks → {partial}/{max_marks}")
        return {
            "marks_awarded": partial,
            "max_marks": max_marks,
            "math_score": 0.2,
            "reason": "Could not evaluate mathematically — partial marks for attempt",
            "details": {},
            "evaluation_type": "fallback"
        }

    return default_result


# ===================== SYMPY EVALUATION =====================

def _sympy_evaluate(student_answer, model_answer, model_expressions, max_marks):
    """
    Full SymPy-based evaluation with expression comparison, step validation,
    and final answer checking.
    """
    scores = {}

    # Check expression equivalences
    if model_expressions:
        expr_scores = []
        for expr in model_expressions:
            score = _compare_expressions(student_answer, expr)
            if score is not None:
                expr_scores.append(score)
        if expr_scores:
            scores["expression_match"] = max(expr_scores)

    # Check final answer
    final_score = _compare_final_answers(student_answer, model_answer)
    if final_score is not None:
        scores["final_answer"] = final_score

    # Check numerical values
    num_score = _compare_numerical_values(student_answer, model_answer)
    if num_score is not None:
        scores["numerical_values"] = num_score

    # Check steps
    step_score = _validate_steps(student_answer, model_answer, model_expressions)
    if step_score is not None:
        scores["step_coverage"] = step_score

    if not scores:
        return None

    # Weighted combination
    weights = {
        "final_answer": 0.40,
        "expression_match": 0.25,
        "numerical_values": 0.20,
        "step_coverage": 0.15
    }

    weighted_sum = 0.0
    weight_total = 0.0
    for key, weight in weights.items():
        if key in scores:
            weighted_sum += scores[key] * weight
            weight_total += weight

    if weight_total == 0:
        return None

    final_score = weighted_sum / weight_total
    marks = round(final_score * max_marks * 2) / 2  # Round to nearest 0.5
    marks = max(0, min(marks, max_marks))

    return {
        "marks_awarded": marks,
        "max_marks": max_marks,
        "math_score": round(final_score, 3),
        "reason": _generate_math_reason(scores, final_score),
        "details": {k: round(v, 3) for k, v in scores.items()},
        "evaluation_type": "sympy"
    }


# ===================== NUMERICAL EVALUATION =====================

def _numerical_evaluate(student_answer, model_answer, model_expressions, max_marks):
    """
    Purely numerical comparison without SymPy.
    Compares extracted numbers from both answers.
    """
    num_score = _compare_numerical_values(student_answer, model_answer)
    if num_score is None:
        return None

    final_score = _compare_final_answers(student_answer, model_answer)
    if final_score is not None:
        # Weight final answer more
        combined = 0.6 * (final_score or 0) + 0.4 * num_score
    else:
        combined = num_score

    marks = round(combined * max_marks * 2) / 2
    marks = max(0, min(marks, max_marks))

    return {
        "marks_awarded": marks,
        "max_marks": max_marks,
        "math_score": round(combined, 3),
        "reason": f"Numerical comparison: {round(combined * 100)}% match",
        "details": {
            "numerical_match": round(num_score, 3),
            "final_answer_match": round(final_score, 3) if final_score else None
        },
        "evaluation_type": "numerical"
    }


# ===================== REASON GENERATION =====================

def _generate_math_reason(scores, final_score):
    """Generate a human-readable reason from math evaluation scores."""
    parts = []

    if scores.get("final_answer", 0) >= 0.9:
        parts.append("Final answer is correct")
    elif scores.get("final_answer", 0) > 0:
        parts.append("Final answer is partially correct")
    else:
        parts.append("Final answer incorrect or not found")

    if scores.get("step_coverage", 0) >= 0.7:
        parts.append("good step-by-step work shown")
    elif scores.get("step_coverage", 0) > 0.3:
        parts.append("some steps shown")
    elif "step_coverage" in scores:
        parts.append("insufficient steps shown")

    if scores.get("numerical_values", 0) >= 0.8:
        parts.append("numerical values match")

    return ". ".join(parts) + "."
