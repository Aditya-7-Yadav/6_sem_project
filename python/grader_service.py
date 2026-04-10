"""
Grader Service Wrapper
----------------------
Wraps short_answer_grader.py and long_answer_grader_alt.py for Node.js integration.
Extended to support multimodal evaluation: text, diagram, math, theorem.

Reads JSON from stdin, calls the appropriate grader, writes JSON to stdout.

Input JSON (via stdin):
{
    "type": "short" | "long",
    "student_answer": "...",
    "model_answer": "...",
    "keywords": { ... },       // required for short, auto-generated if missing
    "max_marks": 5,            // required for long
    // NEW optional fields:
    "content_types": ["text", "diagram"],  // content types for this question
    "diagram_data": { ... },   // structured diagram description from model answer
    "math_expressions": [...], // expected math expressions from model answer
    "image_path": "...",       // path to student's page image (for diagram eval)
    "alignment_confidence": 0.95  // confidence in answer alignment
}

Output JSON (via stdout):
{
    "final_score": 0.85,
    "marks_awarded": 4,
    "details": { ... },
    "diagram_score": 0.7,     // NEW: null if no diagram
    "math_score": null,        // NEW: null if no math
    "feedback": "...",         // NEW: auto-generated feedback
    "content_types_evaluated": ["text", "diagram"]  // NEW: what was evaluated
}
"""

import sys
import os
import json
import re

# Add the python directory to path so we can import the graders
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from short_answer_grader import ShortAnswerGrader
from long_answer_grader_alt import LongAnswerGrader

# Import new evaluators
try:
    from ocr.diagram_evaluator import evaluate_diagram
    DIAGRAM_EVAL_AVAILABLE = True
except ImportError:
    DIAGRAM_EVAL_AVAILABLE = False

try:
    from ocr.math_evaluator import evaluate_math
    MATH_EVAL_AVAILABLE = True
except ImportError:
    MATH_EVAL_AVAILABLE = False


def log_grader(msg):
    """Log to stderr so stdout JSON stays clean."""
    print(f"[GraderService] {msg}", file=sys.stderr, flush=True)

# ===================== KEYWORD AUTO-EXTRACTION =====================
STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "just", "because", "but", "and", "or", "if", "while", "about", "up",
    "which", "who", "whom", "this", "that", "these", "those", "am", "it",
    "its", "my", "we", "our", "your", "his", "her", "they", "them", "what",
    "also", "like", "well", "back", "much", "even", "still", "new", "want",
    "use", "way", "look", "make", "know", "take", "come", "think", "see",
    "get", "give", "go", "say", "she", "he", "one", "two", "first",
    "using", "used", "called", "known", "refers", "refer", "means", "mean",
    "i.e", "eg", "etc", "following", "given"
}


def auto_extract_keywords(model_answer):
    """
    Extract significant keywords from model answer text.
    Returns dict in format expected by ShortAnswerGrader:
    { "keyword": ["keyword", "synonym1"], ... }
    """
    words = re.findall(r'\b[a-z][a-z0-9]*\b', model_answer.lower())
    significant = [w for w in words if w not in STOP_WORDS and len(w) > 2]

    # Count frequency to prioritize important words
    freq = {}
    for w in significant:
        freq[w] = freq.get(w, 0) + 1

    # Take top keywords (max 10)
    sorted_words = sorted(freq.keys(), key=lambda x: freq[x], reverse=True)
    top_keywords = sorted_words[:10]

    keywords = {}
    for word in top_keywords:
        keywords[word] = [word]

    return keywords


# ===================== SINGLETON GRADERS =====================
_short_grader = None
_long_grader = None


def get_short_grader():
    global _short_grader
    if _short_grader is None:
        print("Loading short answer grader model...", file=sys.stderr)
        _short_grader = ShortAnswerGrader()
    return _short_grader


def get_long_grader(max_marks=5):
    global _long_grader
    if _long_grader is None or _long_grader.max_marks != max_marks:
        print(f"Loading long answer grader model (max_marks={max_marks})...", file=sys.stderr)
        _long_grader = LongAnswerGrader(max_marks=max_marks)
    return _long_grader


# ===================== GRADE SINGLE ANSWER =====================
def grade_answer(data):
    answer_type = data.get("type", "short")
    student_answer = data.get("student_answer", "")
    model_answer = data.get("model_answer", "")
    content_types = data.get("content_types", ["text"])
    max_marks = data.get("max_marks", 5 if answer_type == "long" else 1)

    # Determine if this is a multimodal question
    has_diagram = "diagram" in content_types or "graph" in content_types
    has_math = "numerical" in content_types or "math" in content_types
    has_theorem = "theorem" in content_types

    # If it's purely text OR we don't have new evaluators, use existing graders
    if not has_diagram and not has_math:
        result = _grade_text_answer(data, answer_type, student_answer, model_answer, max_marks)
        result["diagram_score"] = None
        result["math_score"] = None
        result["content_types_evaluated"] = ["text"]
        result["feedback"] = _generate_feedback(result)
        return result

    # MULTIMODAL: composite scoring
    log_grader(f"Multimodal grading: content_types={content_types}")
    return _grade_multimodal(data, student_answer, model_answer, max_marks,
                             content_types, has_diagram, has_math)


def _grade_text_answer(data, answer_type, student_answer, model_answer, max_marks):
    """
    Grade a text-only answer using existing ML graders.
    This is the ORIGINAL grading logic — completely unchanged.
    """
    if answer_type == "short":
        keywords = data.get("keywords")
        if not keywords:
            keywords = auto_extract_keywords(model_answer)

        grader = get_short_grader()
        result = grader.evaluate(student_answer, model_answer, keywords)

        # Scale marks to max_marks for short answers
        # ShortAnswerGrader gives 0, 0.5, or 1
        # Scale: 0 -> 0, 0.5 -> max_marks/2, 1 -> max_marks
        result["marks_awarded"] = result["marks_awarded"] * max_marks
        result["max_marks"] = max_marks

        return result

    elif answer_type == "long":
        grader = get_long_grader(max_marks)
        result = grader.evaluate(student_answer, model_answer)
        result["max_marks"] = max_marks
        return result

    else:
        return {"error": f"Unknown type: {answer_type}",
                "marks_awarded": 0, "max_marks": max_marks,
                "final_score": 0, "details": {}}


def _grade_multimodal(data, student_answer, model_answer, max_marks,
                      content_types, has_diagram, has_math):
    """
    Grade a question with mixed content types.
    Uses composite scoring: text_score * weight + diagram_score * weight + math_score * weight.
    """
    results = {}
    weights = {}
    evaluated_types = []

    # --- Text component ---
    # Always evaluate text (even for diagram questions, text may be part of the answer)
    if student_answer and model_answer:
        text_result = _grade_text_answer(
            data, data.get("type", "long"), student_answer, model_answer, max_marks
        )
        text_score = text_result.get("final_score", 0)
        results["text"] = text_result
        evaluated_types.append("text")

        # Weight text higher if it's the primary content type
        if has_diagram or has_math:
            weights["text"] = 0.5
        else:
            weights["text"] = 1.0
    else:
        text_score = 0
        weights["text"] = 0.5 if (has_diagram or has_math) else 1.0

    # --- Diagram component ---
    diagram_score = None
    if has_diagram and DIAGRAM_EVAL_AVAILABLE:
        image_path = data.get("image_path")
        diagram_data = data.get("diagram_data")
        diagram_result = evaluate_diagram(
            image_path=image_path,
            model_diagram_data=diagram_data,
            model_text=model_answer,
            max_marks=max_marks,
            question_number=data.get("question_number", "?")
        )
        diagram_score = diagram_result.get("diagram_score", 0)
        results["diagram"] = diagram_result
        weights["diagram"] = 0.3
        evaluated_types.append("diagram")
    elif has_diagram:
        # Diagram expected but evaluator unavailable — award partial credit
        diagram_score = 0.3
        diagram_result = {
            "marks_awarded": round(diagram_score * max_marks, 1),
            "max_marks": float(max_marks),
            "diagram_score": diagram_score,
            "reason": "Diagram evaluator unavailable — partial credit awarded",
            "details": {},
            "evaluation_type": "unavailable_fallback"
        }
        results["diagram"] = diagram_result
        weights["diagram"] = 0.3
        evaluated_types.append("diagram")

    # --- Math component ---
    math_score = None
    if has_math and MATH_EVAL_AVAILABLE:
        math_result = evaluate_math(
            student_answer=student_answer,
            model_answer=model_answer,
            model_expressions=data.get("math_expressions", []),
            max_marks=max_marks,
            question_number=data.get("question_number", "?")
        )
        math_score = math_result.get("math_score", 0)
        results["math"] = math_result
        weights["math"] = 0.2
        evaluated_types.append("numerical")
    elif has_math:
        weights["math"] = 0.0  # Can't evaluate, redistribute weight
        weights["text"] = weights.get("text", 0.5) + 0.2

    # --- Compute composite score ---
    total_weight = sum(weights.values())
    if total_weight > 0:
        composite_score = 0
        if "text" in results and weights.get("text", 0) > 0:
            composite_score += text_score * (weights["text"] / total_weight)
        if diagram_score is not None and weights.get("diagram", 0) > 0:
            composite_score += diagram_score * (weights["diagram"] / total_weight)
        if math_score is not None and weights.get("math", 0) > 0:
            composite_score += math_score * (weights["math"] / total_weight)
    else:
        composite_score = text_score

    # Convert to marks
    marks_awarded = round(composite_score * max_marks * 2) / 2  # Round to nearest 0.5
    marks_awarded = max(0, min(marks_awarded, max_marks))

    # Build combined details
    combined_details = {}
    if "text" in results:
        combined_details["text_details"] = results["text"].get("details", {})
    if "diagram" in results:
        combined_details["diagram_details"] = results["diagram"].get("details", {})
    if "math" in results:
        combined_details["math_details"] = results["math"].get("details", {})
    combined_details["weights_used"] = weights

    final_result = {
        "final_score": round(composite_score, 3),
        "marks_awarded": marks_awarded,
        "max_marks": max_marks,
        "details": combined_details,
        "diagram_score": round(diagram_score, 3) if diagram_score is not None else None,
        "math_score": round(math_score, 3) if math_score is not None else None,
        "content_types_evaluated": evaluated_types,
    }
    final_result["feedback"] = _generate_feedback(final_result)

    log_grader(f"Multimodal result: {marks_awarded}/{max_marks} "
               f"(text={text_score:.2f}, diagram={diagram_score}, math={math_score})")

    return final_result


def _generate_feedback(result):
    """
    Generate human-readable feedback from grading result.
    """
    marks = result.get("marks_awarded", 0)
    max_m = result.get("max_marks", 1)
    pct = (marks / max_m * 100) if max_m > 0 else 0

    parts = []

    if pct >= 90:
        parts.append("Excellent answer! Well covered all key points.")
    elif pct >= 70:
        parts.append("Good answer with most key concepts covered.")
    elif pct >= 50:
        parts.append("Partial answer. Some important points are missing.")
    elif pct >= 25:
        parts.append("Needs improvement. Several key concepts are missing.")
    elif marks > 0:
        parts.append("Minimal coverage. Review the model answer for key points.")
    else:
        parts.append("No relevant content found. Please refer to the model answer.")

    # Add diagram-specific feedback
    if result.get("diagram_score") is not None:
        d_score = result["diagram_score"]
        if d_score >= 0.8:
            parts.append("Diagram is well drawn and accurate.")
        elif d_score >= 0.5:
            parts.append("Diagram is partially correct but missing some elements.")
        elif d_score > 0:
            parts.append("Diagram needs significant improvement.")
        else:
            parts.append("Diagram was not found or could not be evaluated.")

    # Add math-specific feedback
    if result.get("math_score") is not None:
        m_score = result["math_score"]
        if m_score >= 0.8:
            parts.append("Mathematical solution is correct.")
        elif m_score >= 0.5:
            parts.append("Mathematical approach is correct but has errors.")
        elif m_score > 0:
            parts.append("Mathematical solution needs review.")

    return " ".join(parts)


# ===================== BATCH MODE =====================
def grade_batch(questions):
    """Grade a list of questions in one call (avoids model reload overhead)."""
    results = []
    for q in questions:
        try:
            result = grade_answer(q)
            result["question_number"] = q.get("question_number", "?")
            results.append(result)
        except Exception as e:
            results.append({
                "question_number": q.get("question_number", "?"),
                "error": str(e),
                "marks_awarded": 0,
                "max_marks": q.get("max_marks", 0),
                "final_score": 0,
                "details": {},
                "diagram_score": None,
                "math_score": None,
                "feedback": "Evaluation failed: " + str(e),
                "content_types_evaluated": []
            })
    return results


# ===================== ENTRY POINT =====================
if __name__ == "__main__":
    try:
        raw_input = sys.stdin.read()
        data = json.loads(raw_input)

        # Support both single and batch mode
        if isinstance(data, list):
            # Batch mode: list of questions
            results = grade_batch(data)
            print(json.dumps(results, ensure_ascii=False))
        elif "questions" in data:
            # Batch mode: { "questions": [...] }
            results = grade_batch(data["questions"])
            print(json.dumps(results, ensure_ascii=False))
        else:
            # Single mode
            result = grade_answer(data)
            print(json.dumps(result, ensure_ascii=False))

    except Exception as e:
        error = {"error": str(e)}
        print(json.dumps(error), file=sys.stdout)
        sys.exit(1)
