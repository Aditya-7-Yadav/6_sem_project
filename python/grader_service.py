"""
Grader Service Wrapper
----------------------
Wraps short_answer_grader.py and long_answer_grader_alt.py for Node.js integration.
Reads JSON from stdin, calls the appropriate grader, writes JSON to stdout.

Input JSON (via stdin):
{
    "type": "short" | "long",
    "student_answer": "...",
    "model_answer": "...",
    "keywords": { ... },       // required for short, auto-generated if missing
    "max_marks": 5             // required for long
}

Output JSON (via stdout):
{
    "final_score": 0.85,
    "marks_awarded": 4,
    "details": { ... }
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

    if answer_type == "short":
        keywords = data.get("keywords")
        if not keywords:
            keywords = auto_extract_keywords(model_answer)

        grader = get_short_grader()
        max_marks = data.get("max_marks", 1)
        result = grader.evaluate(student_answer, model_answer, keywords)

        # Scale marks to max_marks for short answers
        # ShortAnswerGrader gives 0, 0.5, or 1
        # Scale: 0 -> 0, 0.5 -> max_marks/2, 1 -> max_marks
        result["marks_awarded"] = result["marks_awarded"] * max_marks
        result["max_marks"] = max_marks

        return result

    elif answer_type == "long":
        max_marks = data.get("max_marks", 5)
        grader = get_long_grader(max_marks)
        result = grader.evaluate(student_answer, model_answer)
        result["max_marks"] = max_marks
        return result

    else:
        return {"error": f"Unknown type: {answer_type}"}


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
                "details": {}
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
