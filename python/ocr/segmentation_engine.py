"""
Segmentation Engine
--------------------
Splits student answer text into question-wise segments DRIVEN BY the
model answer structure. The model answer defines what questions exist;
this engine maps student content to those questions.

Strategy cascade:
  1. Regex-based question marker detection (fastest)
  2. Normalized sub-question detection (handles OCR garbling)
  3. Semantic chunking (paragraph → model question similarity)
  4. Gemini AI boundary detection (most powerful, uses quota)
  5. Full-text distribution fallback (last resort)

Usage:
    from ocr.segmentation_engine import segment_student_answers
    segments = segment_student_answers(
        student_text="...",
        model_structure={"questions": {...}, "question_structure": [...]},
        student_structured=None  # optional: existing OCR structured answers
    )

Output:
{
    "segments": {
        "1(a)": {
            "text": "student answer text for 1(a)...",
            "confidence": 0.95,
            "source": "regex"
        },
        "1(b)": { ... }
    },
    "unmatched_text": "...",
    "strategy_used": "regex"
}
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
from ocr.gemini_client import log, GEMINI_AVAILABLE


def log_seg(msg):
    """Log with module prefix."""
    print(f"[SegmentationEngine] {msg}", file=sys.stderr, flush=True)


# ===================== QUESTION NUMBER NORMALIZATION =====================

def normalize_question_number(qnum):
    """
    Normalize a question number for matching.
    "Q1(a)" → "1(a)", "q 2 (b)" → "2(b)", "Ans 1" → "1"
    """
    if not qnum:
        return ""
    s = str(qnum).strip()
    # Remove common prefixes
    s = re.sub(r'^(?:q(?:uestion)?|ans(?:wer)?|a)\s*', '', s, flags=re.IGNORECASE)
    # Remove leading punctuation (but not opening parens — they're sub-question markers)
    s = re.sub(r'^[-.:;\s]+', '', s)
    
    # Handle malformed sub-questions correctly mapping "3) a)", "3-a", "3a" -> "3(a)"
    s = re.sub(r'(\d+)[\s\(\)-]*([a-zA-Z])\)?', r'\1(\2)', s)
    
    # Normalize spaces in sub-question notation BEFORE stripping trailing punct
    s = re.sub(r'\s+\(\s*', '(', s)
    s = re.sub(r'\s*\)\s*', ')', s)
    # Remove trailing punctuation (but keep closing paren if preceded by a letter)
    s = re.sub(r'[.:;\s]+$', '', s)
    return s.lower().strip()


def get_base_question_number(qnum):
    """
    Extract base question number without sub-question.
    "1(a)" → "1", "2(b)" → "2", "3" → "3"
    """
    normalized = normalize_question_number(qnum)
    return re.sub(r'[\(][a-z][\)]', '', normalized).strip()


# ===================== STRATEGY 1: REGEX MARKERS =====================

# Matches: Q1, Q1., Q1:, Q1), Ans 1, Answer 1, A1, 1., 1), Q-3) a)
ANSWER_HEADER_RE = re.compile(
    r'''
    (?:^|\n)                          # start of text or newline
    \s*
    (?:
        # Q<num>(sub) variants - extremely forgiving of hyphens, spaces, and broken parens
        (?:[Qq](?:uestion)?\s*[-.]?\s*(\d+(?:[\s\(\)-]*[a-zA-Z]\)?)?)\s*[.):;]?\s*(?:[Aa]ns(?:wer)?)?[.):;\s]*)
        |
        # Answer <num> / Ans <num>
        (?:[Aa](?:ns(?:wer)?)\s*(\d+(?:[\s\(\)-]*[a-zA-Z]\)?)?)\s*[.):;\s]*)
        |
        # Ans (a), Ans (b) — sub-question markers
        (?:[Aa]ns\s*(\([a-zA-Z]\))\s*[.):;\s]*)
        |
        # A<num>
        (?:[Aa]\s*(\d+(?:[\s\(\)-]*[a-zA-Z]\)?)?)\s*[.):;\s]+)
        |
        # Bare number: 1., 1), 1:
        (?:(\d+(?:[\s\(\)-]*[a-zA-Z]\)?)?)\s*[.):][\s]*)
    )
    ''',
    re.VERBOSE | re.MULTILINE
)

# Sub-question pattern: Ans (a), Ans (b), etc.
SUB_Q_RE = re.compile(
    r'(?:^|\n)\s*(?:Ans|Am|ans)\s*\(([a-c])\)',
    re.IGNORECASE | re.MULTILINE
)


def _strategy_regex(student_text, model_structure):
    """
    Strategy 1: Find student answer markers using regex and map to model structure.
    """
    model_questions = model_structure.get("question_structure", [])
    if not model_questions:
        return None

    matches = list(ANSWER_HEADER_RE.finditer(student_text))
    if not matches:
        return None

    # Extract matched question numbers and their text spans
    detected = []
    for i, match in enumerate(matches):
        # Find which group matched
        qnum = None
        for g in range(1, 6):
            if match.group(g):
                qnum = match.group(g)
                break
        if not qnum:
            continue

        start_pos = match.end()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(student_text)
        answer_text = student_text[start_pos:end_pos].strip()
        detected.append({
            "raw_number": qnum.strip(),
            "normalized": normalize_question_number(qnum),
            "text": answer_text
        })

    if not detected:
        return None

    log_seg(f"Regex found {len(detected)} answer markers: "
            f"{[d['normalized'] for d in detected]}")

    # Map detected answers to model questions
    segments = {}
    used_detected = set()

    for model_q in model_questions:
        model_norm = normalize_question_number(model_q)
        model_base = get_base_question_number(model_q)

        best_match = None
        best_score = -1

        for idx, det in enumerate(detected):
            if idx in used_detected:
                continue

            det_norm = det["normalized"]
            det_base = get_base_question_number(det["normalized"])

            # Exact match
            if det_norm == model_norm:
                best_match = idx
                best_score = 3
                break

            # Base number match (e.g., model has "1(a)", student wrote "1")
            if det_base == model_base and best_score < 2:
                best_match = idx
                best_score = 2

            # Numeric-only match
            if det_base == model_base and best_score < 1:
                best_match = idx
                best_score = 1

        if best_match is not None:
            used_detected.add(best_match)
            segments[model_q] = {
                "text": detected[best_match]["text"],
                "confidence": min(1.0, best_score / 3),
                "source": "regex",
                "matched_from": detected[best_match]["raw_number"]
            }
        else:
            segments[model_q] = {
                "text": "",
                "confidence": 0.0,
                "source": "regex",
                "matched_from": None
            }

    # Check if enough questions were matched
    matched_count = sum(1 for s in segments.values() if s["text"])
    if matched_count < 1:
        return None

    return {
        "segments": segments,
        "unmatched_text": "",
        "strategy_used": "regex"
    }


# ===================== STRATEGY 2: SUB-QUESTION DETECTION =====================

def _normalize_ocr_text(text):
    """
    Fix common OCR issues where question markers are garbled.
    """
    # Fix garbled "Am (9" → "Ans (a)"
    normalized = re.sub(r'\bAm\s*\(\d', 'Ans (a)', text, flags=re.IGNORECASE)

    # Join "Ans" with following sub-question marker
    normalized = re.sub(
        r'(Ans|Am|ans)\s*\n\s*[=*i%\s]*\n?\s*(\([a-c]\))',
        r'Ans \2', normalized, flags=re.IGNORECASE
    )
    normalized = re.sub(
        r'(Ans|Am|ans)\s*\n\s*(\([a-c]\))',
        r'Ans \2', normalized, flags=re.IGNORECASE
    )
    normalized = re.sub(
        r'(\([a-c]\))\s*\n\s*(Ans|Am|ans)',
        r'Ans \1', normalized, flags=re.IGNORECASE
    )
    normalized = re.sub(
        r'(?:^|\n)\s*(\([a-c]\))\s*\n',
        r'\nAns \1\n', normalized
    )
    return normalized


def _strategy_subquestion(student_text, model_structure):
    """
    Strategy 2: Detect sub-question patterns like Ans(a), Ans(b), etc.
    Infers main question numbers by tracking (a) resets.
    """
    model_questions = model_structure.get("question_structure", [])
    if not model_questions:
        return None

    # Check if model uses sub-questions
    has_subqs = any('(' in str(q) for q in model_questions)
    if not has_subqs:
        return None

    normalized = _normalize_ocr_text(student_text)
    sub_matches = list(SUB_Q_RE.finditer(normalized))

    if len(sub_matches) < 2:
        return None

    log_seg(f"Sub-question detection found {len(sub_matches)} markers: "
            f"{[m.group(1) for m in sub_matches]}")

    # Build sub-question segments
    detected = []
    current_main_q = 0

    for i, match in enumerate(sub_matches):
        sub_letter = match.group(1)

        if sub_letter == 'a':
            current_main_q += 1

        start_pos = match.end()
        end_pos = sub_matches[i + 1].start() if i + 1 < len(sub_matches) else len(normalized)
        answer_text = normalized[start_pos:end_pos].strip()
        answer_text = re.sub(r'^[\s=*\xA1i%\n]+', '', answer_text)

        q_number = f"{current_main_q}({sub_letter})"
        detected.append({"number": q_number, "text": answer_text})

    # Map to model structure
    segments = {}
    detected_lookup = {normalize_question_number(d["number"]): d for d in detected}

    for model_q in model_questions:
        model_norm = normalize_question_number(model_q)
        if model_norm in detected_lookup:
            segments[model_q] = {
                "text": detected_lookup[model_norm]["text"],
                "confidence": 0.85,
                "source": "subquestion",
                "matched_from": detected_lookup[model_norm]["number"]
            }
        else:
            segments[model_q] = {
                "text": "",
                "confidence": 0.0,
                "source": "subquestion",
                "matched_from": None
            }

    matched_count = sum(1 for s in segments.values() if s["text"])
    if matched_count < 1:
        return None

    return {
        "segments": segments,
        "unmatched_text": "",
        "strategy_used": "subquestion"
    }


# ===================== STRATEGY 3: SEMANTIC CHUNKING =====================

def _strategy_semantic(student_text, model_structure):
    """
    Strategy 3: Split text into paragraphs and assign to model questions
    based on semantic similarity using sentence-transformers.
    """
    model_questions = model_structure.get("question_structure", [])
    questions_data = model_structure.get("questions", {})
    if not model_questions or not questions_data:
        return None

    # Split student text into paragraphs
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', student_text) if p.strip()]
    if not paragraphs:
        paragraphs = [s.strip() for s in student_text.split('\n') if len(s.strip()) > 30]

    if not paragraphs:
        return None

    log_seg(f"Semantic chunking: {len(paragraphs)} paragraphs vs "
            f"{len(model_questions)} model questions")

    try:
        from sentence_transformers import SentenceTransformer, util
        import torch
    except ImportError:
        log_seg("sentence-transformers not available, skipping semantic strategy")
        return None

    try:
        # Use the same model as the graders (already cached)
        model = SentenceTransformer("BAAI/bge-small-en-v1.5")

        # Encode model answers
        model_texts = []
        for q_num in model_questions:
            q_data = questions_data.get(q_num, {})
            model_texts.append(q_data.get("text", "") or q_data.get("modelAnswer", ""))

        if not any(model_texts):
            return None

        model_embeddings = model.encode(model_texts, convert_to_tensor=True)
        para_embeddings = model.encode(paragraphs, convert_to_tensor=True)

        # Compute similarity matrix
        sim_matrix = util.cos_sim(para_embeddings, model_embeddings)

        # Assign each paragraph to its best matching model question
        assignments = {}  # question_idx → list of paragraph indices
        for para_idx in range(len(paragraphs)):
            best_q_idx = torch.argmax(sim_matrix[para_idx]).item()
            best_score = sim_matrix[para_idx][best_q_idx].item()

            if best_score > 0.3:  # minimum similarity threshold
                if best_q_idx not in assignments:
                    assignments[best_q_idx] = []
                assignments[best_q_idx].append((para_idx, best_score))

        # Build segments
        segments = {}
        for q_idx, q_num in enumerate(model_questions):
            if q_idx in assignments:
                assigned_paras = assignments[q_idx]
                # Sort by original order
                assigned_paras.sort(key=lambda x: x[0])
                combined_text = "\n".join(paragraphs[p[0]] for p in assigned_paras)
                avg_confidence = sum(p[1] for p in assigned_paras) / len(assigned_paras)
                segments[q_num] = {
                    "text": combined_text,
                    "confidence": round(avg_confidence, 3),
                    "source": "semantic",
                    "matched_from": f"{len(assigned_paras)} paragraphs"
                }
            else:
                segments[q_num] = {
                    "text": "",
                    "confidence": 0.0,
                    "source": "semantic",
                    "matched_from": None
                }

        matched_count = sum(1 for s in segments.values() if s["text"])
        if matched_count < 1:
            return None

        log_seg(f"Semantic chunking matched {matched_count}/{len(model_questions)} questions")

        return {
            "segments": segments,
            "unmatched_text": "",
            "strategy_used": "semantic"
        }

    except Exception as e:
        log_seg(f"Semantic chunking failed: {e}")
        return None


# ===================== STRATEGY 4: GEMINI BOUNDARY DETECTION =====================

def _strategy_gemini(student_text, model_structure):
    """
    Strategy 4: Use Gemini AI to identify question boundaries
    in the student's OCR text, guided by the model structure.
    """
    if not GEMINI_AVAILABLE:
        return None

    from ocr.gemini_client import gemini_analyze_text
    import json

    model_questions = model_structure.get("question_structure", [])
    if not model_questions:
        return None

    prompt = f"""You are analyzing OCR text from a student's handwritten answer sheet.
The model answer has these questions: {json.dumps(model_questions)}

Your task: Split the student's text into segments, one per model question.
The student may have answered questions in any order or may have skipped some.

Student's OCR text:
{student_text[:6000]}

Return a JSON object mapping each model question to the student's answer text:
{{
    "{model_questions[0]}": "student's answer for this question...",
    "{model_questions[1] if len(model_questions) > 1 else '...'}": "..."
}}

RULES:
- Map text to the most appropriate question based on content
- If no answer found for a question, use empty string ""
- Include ALL student text — don't discard any content
- Return ONLY valid JSON, no explanations
"""

    log_seg("Using Gemini for boundary detection...")
    response = gemini_analyze_text(prompt)

    if not response:
        return None

    # Parse response
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)

    try:
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            return None

        segments = {}
        for q_num in model_questions:
            text = str(parsed.get(q_num, "")).strip()
            segments[q_num] = {
                "text": text,
                "confidence": 0.7 if text else 0.0,
                "source": "gemini",
                "matched_from": "AI boundary detection"
            }

        matched_count = sum(1 for s in segments.values() if s["text"])
        if matched_count < 1:
            return None

        log_seg(f"Gemini matched {matched_count}/{len(model_questions)} questions")

        return {
            "segments": segments,
            "unmatched_text": "",
            "strategy_used": "gemini"
        }

    except json.JSONDecodeError:
        log_seg("Failed to parse Gemini segmentation response")
        return None


# ===================== STRATEGY 5: FULL-TEXT FALLBACK =====================

def _strategy_fulltext(student_text, model_structure):
    """
    Strategy 5 (last resort): Distribute the full text to all model questions.
    The grader's semantic similarity will still produce meaningful scores.
    """
    model_questions = model_structure.get("question_structure", [])
    if not model_questions:
        return None

    log_seg(f"Full-text fallback: distributing {len(student_text)} chars "
            f"to all {len(model_questions)} questions")

    segments = {}
    for q_num in model_questions:
        segments[q_num] = {
            "text": student_text,
            "confidence": 0.2,
            "source": "fulltext_fallback",
            "matched_from": "entire text distributed"
        }

    return {
        "segments": segments,
        "unmatched_text": "",
        "strategy_used": "fulltext_fallback"
    }


# ===================== MAIN ENTRY POINT =====================

def segment_student_answers(student_text, model_structure, student_structured=None):
    """
    Segment student answer text according to model answer structure.

    Args:
        student_text (str): Full OCR text from student answer sheet.
        model_structure (dict): Output from model_answer_processor.
            Must contain "question_structure" and "questions" keys.
        student_structured (list): Optional existing structured answers from OCR
            (list of dicts with "question_number" and "answer_text").

    Returns:
        dict: Segmented student answers mapped to model questions.
    """
    if not student_text or not student_text.strip():
        log_seg("Empty student text — returning empty segments")
        model_questions = model_structure.get("question_structure", [])
        return {
            "segments": {
                q: {"text": "", "confidence": 0.0, "source": "empty"}
                for q in model_questions
            },
            "unmatched_text": "",
            "strategy_used": "empty_input"
        }

    # If we already have structured answers from OCR, try using them first
    if student_structured and len(student_structured) > 1:
        result = _use_existing_structured(student_structured, model_structure)
        if result:
            log_seg(f"Used existing OCR structured answers (strategy: existing_ocr)")
            return result

    # Cascade through strategies
    strategies = [
        ("regex", _strategy_regex),
        ("subquestion", _strategy_subquestion),
        ("semantic", _strategy_semantic),
        ("gemini", _strategy_gemini),
        ("fulltext", _strategy_fulltext),
    ]

    for name, strategy_fn in strategies:
        log_seg(f"Trying strategy: {name}...")
        result = strategy_fn(student_text, model_structure)
        if result:
            matched = sum(1 for s in result["segments"].values() if s["text"])
            total = len(result["segments"])
            log_seg(f"Strategy '{name}' succeeded: "
                    f"{matched}/{total} questions matched")
            return result

    # Should never reach here (fulltext always succeeds), but just in case
    log_seg("All strategies exhausted — returning empty segments")
    model_questions = model_structure.get("question_structure", [])
    return {
        "segments": {
            q: {"text": "", "confidence": 0.0, "source": "failed"}
            for q in model_questions
        },
        "unmatched_text": student_text,
        "strategy_used": "all_failed"
    }


def _use_existing_structured(student_structured, model_structure):
    """
    Map existing structured answers (from OCR extraction) to model structure.
    """
    model_questions = model_structure.get("question_structure", [])
    if not model_questions:
        return None

    # Build lookup from student structured answers
    student_lookup = {}
    for sa in student_structured:
        q_num = sa.get("question_number", "")
        text = sa.get("answer_text", "") or sa.get("answerText", "")
        if q_num and text:
            normalized = normalize_question_number(q_num)
            student_lookup[normalized] = text

    segments = {}
    matched_count = 0

    for model_q in model_questions:
        model_norm = normalize_question_number(model_q)
        model_base = get_base_question_number(model_q)

        # Try exact match
        text = student_lookup.get(model_norm, "")

        # Try base number match
        if not text:
            text = student_lookup.get(model_base, "")

        if text:
            matched_count += 1

        segments[model_q] = {
            "text": text,
            "confidence": 0.9 if text else 0.0,
            "source": "existing_ocr",
            "matched_from": model_norm if text else None
        }

    total_questions = len(model_questions)
    # Determine acceptance threshold: require at least half of questions matched,
    # with a minimum of 2 if total_questions > 2, otherwise require all.
    if total_questions <= 2:
        threshold = total_questions
    else:
        threshold = max(2, total_questions // 2)
    if matched_count < threshold:
        log_seg(f"_use_existing_structured: only {matched_count}/{total_questions} matched (threshold {threshold}) — skipping")
        return None

    return {
        "segments": segments,
        "unmatched_text": "",
        "strategy_used": "existing_ocr"
    }
