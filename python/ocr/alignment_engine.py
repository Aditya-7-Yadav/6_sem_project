"""
Alignment Engine
-----------------
Maps student answer segments to model answer segments using a combination
of question number matching and semantic similarity.

The alignment engine takes:
  - Segmented student answers (from segmentation_engine.py)
  - Model answer structure (from model_answer_processor.py)

And produces a verified, high-confidence alignment with:
  - Per-question alignment confidence scores
  - Content type information for routing to the right evaluator
  - Warnings for misalignments or missing answers

Uses numpy cosine similarity (no FAISS needed at exam scale).

Usage:
    from ocr.alignment_engine import align_answers
    aligned = align_answers(student_segments, model_structure)

Output:
{
    "aligned_pairs": [
        {
            "question_number": "1(a)",
            "student_text": "...",
            "model_text": "...",
            "model_keywords": [...],
            "content_types": ["text", "diagram"],
            "max_marks": 5,
            "answer_type": "long",
            "alignment_confidence": 0.95,
            "alignment_source": "regex",
            "diagram_data": {...} or null,
            "math_expressions": [],
        }
    ],
    "summary": {
        "total_questions": 10,
        "matched_questions": 8,
        "high_confidence": 7,
        "low_confidence": 1,
        "unmatched": 2,
        "overall_confidence": 0.85
    }
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


def log_align(msg):
    """Log with module prefix."""
    print(f"[AlignmentEngine] {msg}", file=sys.stderr, flush=True)


# ===================== SEMANTIC SIMILARITY =====================

_embed_model = None


def _get_embed_model():
    """
    Lazy-load the sentence-transformer model.
    Reuses the same model instance as the graders (BAAI/bge-small-en-v1.5).
    """
    global _embed_model
    if _embed_model is not None:
        return _embed_model

    try:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer("BAAI/bge-small-en-v1.5")
        log_align("Loaded embedding model for alignment")
        return _embed_model
    except ImportError:
        log_align("sentence-transformers not available — semantic verification disabled")
        return None


def compute_semantic_similarity(text_a, text_b):
    """
    Compute cosine similarity between two texts using sentence embeddings.
    Returns float in [0, 1] or None if embedding model unavailable.
    """
    model = _get_embed_model()
    if model is None:
        return None

    if not text_a or not text_b:
        return 0.0

    try:
        from sentence_transformers import util
        embeddings = model.encode([text_a[:512], text_b[:512]], convert_to_tensor=True)
        similarity = util.cos_sim(embeddings[0], embeddings[1]).item()
        return max(0.0, min(1.0, similarity))
    except Exception as e:
        log_align(f"Semantic similarity computation failed: {e}")
        return None


# ===================== KEYWORD OVERLAP =====================

def compute_keyword_overlap(student_text, model_keywords):
    """
    Compute what fraction of model keywords appear in the student's answer.
    Returns float in [0, 1].
    """
    if not model_keywords or not student_text:
        return 0.0

    student_lower = student_text.lower()
    matched = 0
    for keyword in model_keywords:
        if keyword.lower() in student_lower:
            matched += 1

    return matched / len(model_keywords) if model_keywords else 0.0


# ===================== ALIGNMENT CONFIDENCE BOOSTING =====================

def _compute_alignment_confidence(segment_confidence, semantic_sim, keyword_overlap):
    """
    Combine multiple signals into a final alignment confidence score.

    Signals:
        - segment_confidence: from segmentation engine (how sure we are about the mapping)
        - semantic_sim: how similar the student text is to the model answer
        - keyword_overlap: what fraction of model keywords appear in student text
    """
    weights = {
        "segment": 0.5,
        "semantic": 0.3,
        "keyword": 0.2
    }

    # Handle None values
    if semantic_sim is None:
        # Without semantic verification, rely more on segment confidence
        weights = {"segment": 0.7, "semantic": 0.0, "keyword": 0.3}
        semantic_sim = 0.0

    confidence = (
        weights["segment"] * segment_confidence
        + weights["semantic"] * semantic_sim
        + weights["keyword"] * keyword_overlap
    )

    return round(min(1.0, max(0.0, confidence)), 3)


# ===================== MAIN ALIGNMENT =====================

def align_answers(student_segments, model_structure):
    """
    Align student answer segments with model answer structure.

    Args:
        student_segments (dict): Output from segmentation_engine.segment_student_answers().
            Must contain "segments" key.
        model_structure (dict): Output from model_answer_processor.process_model_answer().
            Must contain "questions" and "question_structure" keys.

    Returns:
        dict: Aligned pairs with confidence scores and evaluation metadata.
    """
    segments = student_segments.get("segments", {})
    strategy_used = student_segments.get("strategy_used", "unknown")

    model_questions = model_structure.get("question_structure", [])
    questions_data = model_structure.get("questions", {})

    if not model_questions:
        log_align("No model questions — nothing to align")
        return {
            "aligned_pairs": [],
            "summary": _empty_summary()
        }

    log_align(f"Aligning {len(segments)} student segments to "
              f"{len(model_questions)} model questions "
              f"(segmentation strategy: {strategy_used})")

    aligned_pairs = []
    high_confidence_count = 0
    low_confidence_count = 0
    unmatched_count = 0

    for q_num in model_questions:
        # Get model data
        model_q = questions_data.get(q_num, {})
        model_text = model_q.get("text", "") or model_q.get("modelAnswer", "")
        model_keywords = model_q.get("keywords", [])
        content_types = model_q.get("content_types", model_q.get("contentTypes", ["text"]))
        max_marks = model_q.get("marks", model_q.get("maxMarks", 0))
        answer_type = model_q.get("type", "long")
        diagram_data = model_q.get("diagram", model_q.get("diagramData"))
        math_expressions = model_q.get("math_expressions",
                                       model_q.get("mathExpressions", []))
        
        # Ensure math is actively routed to the grader even if the LLM forgot to add it to the array
        has_math = model_q.get("has_math", model_q.get("hasMath", False))
        if has_math and "math" not in content_types and "numerical" not in content_types:
            content_types.append("math")

        # Get student segment
        segment = segments.get(q_num, {})
        student_text = segment.get("text", "")
        segment_confidence = segment.get("confidence", 0.0)
        segment_source = segment.get("source", "unknown")

        # Compute alignment verification signals
        semantic_sim = None
        keyword_overlap = 0.0

        if student_text and model_text:
            semantic_sim = compute_semantic_similarity(student_text, model_text)
            keyword_overlap = compute_keyword_overlap(student_text, model_keywords)

        # Compute final alignment confidence
        alignment_confidence = _compute_alignment_confidence(
            segment_confidence, semantic_sim, keyword_overlap
        )

        # Classify confidence level
        if not student_text:
            unmatched_count += 1
        elif alignment_confidence >= 0.5:
            high_confidence_count += 1
        else:
            low_confidence_count += 1

        aligned_pairs.append({
            "question_number": q_num,
            "student_text": student_text,
            "model_text": model_text,
            "model_keywords": model_keywords,
            "content_types": content_types,
            "max_marks": max_marks,
            "answer_type": answer_type,
            "alignment_confidence": alignment_confidence,
            "alignment_source": segment_source,
            "diagram_data": diagram_data,
            "math_expressions": math_expressions,
            # Verification details
            "verification": {
                "semantic_similarity": round(semantic_sim, 3) if semantic_sim is not None else None,
                "keyword_overlap": round(keyword_overlap, 3),
                "segment_confidence": segment_confidence
            }
        })

    # Compute summary
    total = len(model_questions)
    matched = high_confidence_count + low_confidence_count
    overall_confidence = (
        sum(p["alignment_confidence"] for p in aligned_pairs) / total
        if total > 0 else 0.0
    )

    summary = {
        "total_questions": total,
        "matched_questions": matched,
        "high_confidence": high_confidence_count,
        "low_confidence": low_confidence_count,
        "unmatched": unmatched_count,
        "overall_confidence": round(overall_confidence, 3),
        "segmentation_strategy": strategy_used
    }

    log_align(f"Alignment complete: {matched}/{total} matched "
              f"(high={high_confidence_count}, low={low_confidence_count}, "
              f"unmatched={unmatched_count}), "
              f"overall_confidence={overall_confidence:.3f}")

    return {
        "aligned_pairs": aligned_pairs,
        "summary": summary
    }


def _empty_summary():
    """Return an empty alignment summary."""
    return {
        "total_questions": 0,
        "matched_questions": 0,
        "high_confidence": 0,
        "low_confidence": 0,
        "unmatched": 0,
        "overall_confidence": 0.0,
        "segmentation_strategy": "none"
    }


# ===================== UTILITY: ALIGNED PAIRS → GRADING INPUT =====================

def to_grading_input(alignment_result):
    """
    Convert aligned pairs to the format expected by grader_service.py.

    Returns list of dicts ready for grading:
    [
        {
            "question_number": "1(a)",
            "type": "long",
            "student_answer": "...",
            "model_answer": "...",
            "max_marks": 5,
            "keywords": {...},
            "content_types": ["text", "diagram"],
            "diagram_data": {...},
            "math_expressions": [...],
            "alignment_confidence": 0.95
        }
    ]
    """
    pairs = alignment_result.get("aligned_pairs", [])
    grading_input = []

    for pair in pairs:
        # Build keywords dict in the format ShortAnswerGrader expects
        keywords_dict = {}
        for kw in pair.get("model_keywords", []):
            keywords_dict[kw] = [kw]

        grading_input.append({
            "question_number": pair["question_number"],
            "type": pair["answer_type"],
            "student_answer": pair["student_text"],
            "model_answer": pair["model_text"],
            "max_marks": pair["max_marks"],
            "keywords": keywords_dict,
            "content_types": pair["content_types"],
            "diagram_data": pair["diagram_data"],
            "math_expressions": pair["math_expressions"],
            "alignment_confidence": pair["alignment_confidence"]
        })

    return grading_input
