"""
Model Answer Processor
-----------------------
Processes model answer PDFs/text into a rich structured JSON representation.

Extracts per question:
  - Text content
  - Keywords / key concepts
  - Diagram descriptions (structural representation)
  - Mathematical expressions
  - Marks allocation
  - Content type classification

Uses Gemini Vision for PDF understanding with regex fallback.

Usage (standalone):
    python -m ocr.model_answer_processor --input <pdf_or_txt_path> --output <json_path>

Usage (as module):
    from ocr.model_answer_processor import process_model_answer
    result = process_model_answer("/path/to/model_answer.pdf")

Output structure:
{
    "questions": {
        "1(a)": {
            "text": "...",
            "keywords": [...],
            "content_types": ["text"],
            "diagram": null,
            "math_expressions": [],
            "marks": 5,
            "type": "long"
        }
    },
    "total_marks": 75,
    "question_structure": ["1(a)", "1(b)", "2(a)", ...]
}
"""

import os
import sys
import json
import re
import argparse

# --------------- Path Setup ---------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_DIR = os.path.dirname(SCRIPT_DIR)
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)

# --------------- Load Environment ---------------
from dotenv import load_dotenv
load_dotenv(os.path.join(PYTHON_DIR, '.env'))

# --------------- Imports ---------------
from ocr.gemini_client import (
    gemini_analyze_image, gemini_analyze_text,
    log, GEMINI_AVAILABLE
)

# Reuse existing OCR utilities
from ocr_service import pdf_to_images


def log_map(msg):
    """Log with module prefix."""
    print(f"[ModelAnswerProcessor] {msg}", file=sys.stderr, flush=True)


# ===================== STOP WORDS FOR KEYWORD EXTRACTION =====================
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
    "i.e", "eg", "etc", "following", "given", "answer", "question",
    "marks", "mark", "explain", "define", "describe", "discuss", "write",
}


# ===================== GEMINI PROMPTS =====================

MODEL_ANSWER_EXTRACTION_PROMPT = """You are analyzing a model answer sheet for an exam. 
This is the CORRECT/EXPECTED answer key that students' answers will be graded against.

The document may contain a tabular structure (e.g., Q.No, Description of Question, Marks, CO, EO).

For EACH question or sub-question on this page, extract ALL of the exact details. Be thorough and precise.

CRITICAL CONSTRAINTS:
1. LUMP SUB-QUESTIONS INTO PARENTS: If a specific parent question (e.g., Q.1(a)) contains multiple sub-parts (e.g., i, ii, iii), DO NOT extract the sub-parts separately! Combine all of their text, requirements, and keywords into the single parent `1(a)` JSON element. The `marks` for `1(a)` should be the total marks of that parent row (e.g., 3 marks).
2. NO "OR" ALTERNATIVES: To prevent the total exam marks from exceeding the intended maximum (20 marks), COMPLETELY IGNORE AND SKIP any alternative optional questions explicitly labelled "OR". 
3. DO NOT FRACTURE PARAGRAPHS: If an answer contains a numbered list (e.g., 1. Openness, 2. Conscientiousness...), DO NOT treat these bullets as separate questions. An entire essay or table describing one question must remain cohesive inside its parent.

Return a JSON array where each element represents one primary question/sub-question matching the student's highest-level answer format:

[
    {
        "question_number": "1(a)",
        "text": "The complete combined text of the model answer for 1(a), including parts i, ii, and iii...",
        "keywords": ["keyword1", "keyword2", "keyword3"],
        "content_types": ["text"],
        "marks": 3,
        "has_diagram": false,
        "diagram_description": null,
        "diagram_elements": null,
        "diagram_connections": null,
        "has_math": false,
        "math_expressions": []
    }
]

RULES:
- "question_number": Use the highly specific compound number if nested (e.g., "1(a) i", "2(b)", "3"). Do not use "Q".
- "text": The FULL model answer text for this specific segment. Include ALL content from the description column.
- "keywords": 5-15 important domain-specific terms/concepts that a student MUST mention for this specific segment.
- "content_types": Array of types present: "text", "diagram", "graph", "numerical", "theorem"
- "marks": The integer marks allocated to this specific sub-question. Look for "(1 mark)", "[2 marks]", or the dedicated Marks column.
- "has_diagram": true if this specific answer includes any diagram, figure, flowchart, circuit, or pyramid.
- "diagram_description": If has_diagram, describe the diagram in 1-2 sentences. Use the diagram image to generate this!
- "diagram_elements": If has_diagram, list all labeled elements/nodes/components/levels.
- "diagram_connections": If has_diagram, list connections as [["from", "to"], ...]
- "has_math": true if the answer contains equations, formulas, numerical proofs
- "math_expressions": If has_math, list each expression/formula as a string

Return ONLY valid JSON array. No markdown formatting, no explanations.
If the page has no valid primary questions, return: []
"""


# ===================== KEYWORD EXTRACTION =====================

def extract_keywords(text, max_keywords=15):
    """
    Extract significant keywords from model answer text.
    Uses frequency-based extraction with stop word filtering.
    """
    if not text:
        return []

    words = re.findall(r'\b[a-z][a-z0-9-]*\b', text.lower())
    significant = [w for w in words if w not in STOP_WORDS and len(w) > 2]

    # Count frequency
    freq = {}
    for w in significant:
        freq[w] = freq.get(w, 0) + 1

    # Also extract multi-word phrases (bigrams)
    phrases = []
    word_list = text.lower().split()
    for i in range(len(word_list) - 1):
        w1 = re.sub(r'[^a-z0-9]', '', word_list[i])
        w2 = re.sub(r'[^a-z0-9]', '', word_list[i + 1])
        if (w1 and w2 and w1 not in STOP_WORDS and w2 not in STOP_WORDS
                and len(w1) > 2 and len(w2) > 2):
            phrase = f"{w1} {w2}"
            phrases.append(phrase)

    # Combine single words and phrases
    sorted_words = sorted(freq.keys(), key=lambda x: freq[x], reverse=True)

    # Take top single keywords
    top_singles = sorted_words[:max_keywords]

    # Add top phrases (deduplicate with singles)
    phrase_freq = {}
    for p in phrases:
        phrase_freq[p] = phrase_freq.get(p, 0) + 1
    top_phrases = sorted(phrase_freq.keys(), key=lambda x: phrase_freq[x], reverse=True)[:5]

    # Combine, keeping unique
    keywords = list(top_singles)
    for p in top_phrases:
        if p not in keywords:
            keywords.append(p)

    return keywords[:max_keywords]


# ===================== REGEX FALLBACK PARSER =====================

def parse_model_answer_text_regex(text):
    """
    Parse model answer text using regex patterns.
    This is the fallback when Gemini is unavailable.
    Handles formats like:
      Q1 [5 marks] Answer text...
      Q1(a) [3] Answer text...
      1. [2 marks] Answer text...
    """
    if not text or not text.strip():
        return {}

    # Pattern: Q<num> or <num>. or <num>) followed by [<marks>] or (<marks>)
    question_pattern = re.compile(
        r'(?:^|\n)\s*(?:Q|q)?((\d+)(?:\([a-z]\))?)\s*[.):]?\s*'
        r'[\[\(]\s*(\d+)\s*(?:marks?)?\s*[\]\)]',
        re.MULTILINE
    )

    matches = list(question_pattern.finditer(text))

    if not matches:
        log_map("Regex fallback: no question patterns found")
        return {}

    questions = {}
    for i, match in enumerate(matches):
        q_number = match.group(1)
        marks = int(match.group(3))

        # Extract answer text (from end of header to start of next header)
        start_pos = match.end()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        answer_text = text[start_pos:end_pos].strip()

        # Determine type
        q_type = "short" if marks < 3 else "long"

        # Detect content types
        content_types = ["text"]
        has_diagram = bool(re.search(
            r'\b(diagram|figure|draw|sketch|flowchart|circuit|illustration)\b',
            answer_text, re.IGNORECASE
        ))
        has_math = bool(re.search(
            r'[=+\-*/^].*[=+\-*/^]|\\frac|\\sqrt|\bequation\b|\bformula\b',
            answer_text, re.IGNORECASE
        ))
        has_numerical = bool(re.search(
            r'\b(calculate|compute|solve|find the value)\b',
            answer_text, re.IGNORECASE
        ))
        has_theorem = bool(re.search(
            r'\b(theorem|prove|proof|derive|derivation|lemma)\b',
            answer_text, re.IGNORECASE
        ))

        if has_diagram:
            content_types.append("diagram")
        if has_math or has_numerical:
            content_types.append("numerical")
        if has_theorem:
            content_types.append("theorem")

        # Extract keywords
        keywords = extract_keywords(answer_text)

        questions[q_number] = {
            "text": answer_text,
            "keywords": keywords,
            "content_types": content_types,
            "diagram": None,
            "math_expressions": [],
            "marks": marks,
            "type": q_type
        }

    log_map(f"Regex fallback: extracted {len(questions)} questions")
    return questions


# ===================== GEMINI-BASED PROCESSOR =====================

def _process_page_with_gemini(image_path, page_number):
    """
    Process a single page image through Gemini vision.
    Returns list of question dicts extracted from this page.
    """
    log_map(f"Processing page {page_number} with Gemini Vision...")

    response = gemini_analyze_image(image_path, MODEL_ANSWER_EXTRACTION_PROMPT)

    if not response:
        log_map(f"Gemini returned empty response for page {page_number}")
        return []

    # Parse JSON response
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)

    try:
        parsed = json.loads(cleaned)
        if not isinstance(parsed, list):
            if isinstance(parsed, dict) and "questions" in parsed:
                parsed = parsed["questions"]
            elif isinstance(parsed, dict):
                parsed = [parsed]
            else:
                log_map(f"Page {page_number}: unexpected response type {type(parsed)}")
                return []

        log_map(f"Page {page_number}: Gemini extracted {len(parsed)} question(s)")
        return parsed

    except json.JSONDecodeError as e:
        log_map(f"Page {page_number}: Failed to parse Gemini JSON: {e}")
        log_map(f"Raw response (first 300): {response[:300]}")
        return []


def _normalize_question(raw_item):
    """
    Normalize a raw question dict from Gemini into our standard format.
    """
    q_number = str(raw_item.get("question_number", "")).strip()
    if not q_number:
        return None

    # Clean question number: remove "Q" prefix if present
    q_number = re.sub(r'^[Qq]\s*', '', q_number).strip()

    text = str(raw_item.get("text", "")).strip()
    keywords = raw_item.get("keywords", [])
    if not isinstance(keywords, list):
        keywords = []
    keywords = [str(k).strip() for k in keywords if k]

    # If Gemini didn't extract enough keywords, supplement with our own
    if len(keywords) < 5 and text:
        auto_keywords = extract_keywords(text)
        for k in auto_keywords:
            if k not in keywords:
                keywords.append(k)
            if len(keywords) >= 15:
                break

    content_types = raw_item.get("content_types", ["text"])
    if not isinstance(content_types, list):
        content_types = ["text"]

    marks = raw_item.get("marks", 0)
    try:
        marks = int(marks)
    except (ValueError, TypeError):
        marks = 0

    q_type = "short" if marks < 3 else "long"

    # Build diagram data
    diagram_data = None
    if raw_item.get("has_diagram"):
        if "diagram" not in content_types:
            content_types.append("diagram")
        diagram_data = {
            "description": str(raw_item.get("diagram_description", "")).strip(),
            "elements": raw_item.get("diagram_elements") or [],
            "connections": raw_item.get("diagram_connections") or []
        }

    # Build math expressions
    math_expressions = raw_item.get("math_expressions", [])
    if not isinstance(math_expressions, list):
        math_expressions = []
    if raw_item.get("has_math") and "numerical" not in content_types:
        content_types.append("numerical")

    return {
        "question_number": q_number,
        "text": text,
        "keywords": keywords,
        "content_types": content_types,
        "diagram": diagram_data,
        "math_expressions": math_expressions,
        "marks": marks,
        "type": q_type
    }


def _merge_multi_page_questions(all_page_results):
    """
    Merge question data that spans multiple pages.
    If the same question number appears on multiple pages, concatenate the text.
    """
    merged = {}
    order = []

    for page_questions in all_page_results:
        for raw_q in page_questions:
            normalized = _normalize_question(raw_q)
            if not normalized:
                continue

            q_num = normalized["question_number"]

            if q_num in merged:
                # Append text from subsequent pages
                existing = merged[q_num]
                existing["text"] += "\n" + normalized["text"]

                # Merge keywords (deduplicate)
                for k in normalized["keywords"]:
                    if k not in existing["keywords"]:
                        existing["keywords"].append(k)

                # Merge content types
                for ct in normalized["content_types"]:
                    if ct not in existing["content_types"]:
                        existing["content_types"].append(ct)

                # Use diagram data if newly found
                if normalized["diagram"] and not existing["diagram"]:
                    existing["diagram"] = normalized["diagram"]

                # Merge math expressions
                existing["math_expressions"].extend(normalized["math_expressions"])

                # Use marks if not set
                if not existing["marks"] and normalized["marks"]:
                    existing["marks"] = normalized["marks"]
            else:
                merged[q_num] = normalized
                order.append(q_num)

    return merged, order


# ===================== MAIN PROCESSOR =====================

def process_model_answer(file_path, output_dir=None):
    """
    Process a model answer file (PDF or TXT) into structured JSON.

    Args:
        file_path (str): Path to the model answer PDF or TXT file.
        output_dir (str): Optional directory for intermediate files (page images).

    Returns:
        dict: Structured model answer with question-wise breakdown.
    """
    ext = os.path.splitext(file_path)[1].lower()
    log_map(f"Processing model answer: {file_path} (type: {ext})")

    if ext == ".txt":
        return _process_txt_file(file_path)
    elif ext == ".pdf":
        return _process_pdf_file(file_path, output_dir)
    else:
        log_map(f"Unsupported file type: {ext}")
        return {"error": f"Unsupported file type: {ext}"}


def _process_txt_file(file_path):
    """Process a plain text model answer file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
    except Exception as e:
        return {"error": f"Failed to read file: {e}"}

    # Try Gemini text analysis first for richer extraction
    questions = {}
    question_structure = []

    if GEMINI_AVAILABLE:
        prompt = (
            MODEL_ANSWER_EXTRACTION_PROMPT
            + "\n\nMODEL ANSWER TEXT:\n"
            + text[:8000]
        )
        response = gemini_analyze_text(prompt)
        if response:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
                cleaned = re.sub(r'\n?```\s*$', '', cleaned)
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    for raw_q in parsed:
                        normalized = _normalize_question(raw_q)
                        if normalized:
                            q_num = normalized["question_number"]
                            questions[q_num] = normalized
                            question_structure.append(q_num)
            except json.JSONDecodeError:
                pass

    # Fallback to regex if Gemini didn't produce results
    if not questions:
        questions = parse_model_answer_text_regex(text)
        question_structure = list(questions.keys())

    total_marks = sum(q.get("marks", 0) for q in questions.values())

    result = {
        "questions": questions,
        "total_marks": total_marks,
        "question_structure": question_structure,
        "source_type": "txt",
        "processing_mode": "gemini" if GEMINI_AVAILABLE and questions else "regex"
    }

    log_map(f"TXT processing complete: {len(questions)} questions, {total_marks} total marks")
    return result


def _process_pdf_file(file_path, output_dir=None):
    """Process a PDF model answer file using Gemini Vision."""
    import time

    if not output_dir:
        output_dir = os.path.join(
            os.path.dirname(file_path),
            f"model_answer_processing_{os.path.splitext(os.path.basename(file_path))[0]}"
        )

    os.makedirs(output_dir, exist_ok=True)

    # Step 1: Convert PDF to images
    try:
        images = pdf_to_images(file_path, output_dir, dpi=200)
        log_map(f"PDF converted to {len(images)} page images")
    except (ImportError, Exception) as e:
        log_map(f"PDF to image conversion failed: {e}")
        log_map("Attempting text-only extraction...")
        return _process_pdf_text_fallback(file_path)

    if not images:
        return {"error": "No pages extracted from PDF"}

    # Step 2: Process each page with Gemini
    if not GEMINI_AVAILABLE:
        log_map("Gemini not available — falling back to text extraction")
        return _process_pdf_text_fallback(file_path)

    all_page_results = []
    for idx, img_path in enumerate(images):
        page_num = idx + 1
        page_questions = _process_page_with_gemini(img_path, page_num)
        all_page_results.append(page_questions)

        # Rate limiting
        if idx < len(images) - 1:
            time.sleep(1)

    # Step 3: Merge multi-page questions
    questions, question_structure = _merge_multi_page_questions(all_page_results)

    if not questions:
        log_map("Gemini extracted no questions — falling back to text extraction")
        return _process_pdf_text_fallback(file_path)

    total_marks = sum(q.get("marks", 0) for q in questions.values())

    result = {
        "questions": questions,
        "total_marks": total_marks,
        "question_structure": question_structure,
        "source_type": "pdf",
        "processing_mode": "gemini_vision",
        "pages_processed": len(images)
    }

    log_map(f"PDF processing complete: {len(questions)} questions, "
            f"{total_marks} total marks from {len(images)} pages")
    return result


def _process_pdf_text_fallback(file_path, page_images=None):
    """
    Fallback: extract text from PDF and parse with regex.
    Used when Gemini/OpenRouter are unavailable or image conversion fails.
    
    Tries in order:
      1. pdftotext (if available on system)
      2. OCR Space on existing page images (if images were already converted)
      3. Raw text read (last resort, unlikely to work for real PDFs)
    """
    text = ""

    # Strategy 1: pdftotext
    try:
        import subprocess
        result = subprocess.run(
            ['pdftotext', file_path, '-'],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            text = result.stdout
            log_map(f"pdftotext extracted {len(text)} chars")
    except (FileNotFoundError, RuntimeError, subprocess.TimeoutExpired):
        log_map("pdftotext not available or failed")

    # Strategy 2: OCR Space on page images
    if not text.strip() and page_images:
        log_map(f"Trying OCR Space on {len(page_images)} page images...")
        try:
            from ocr_service import run_ocr_on_image
            all_text = []
            for img_path in page_images:
                try:
                    page_text = run_ocr_on_image(img_path)
                    if page_text:
                        all_text.append(page_text)
                except Exception as e:
                    log_map(f"OCR failed for {os.path.basename(img_path)}: {e}")
            if all_text:
                text = "\n\n".join(all_text)
                log_map(f"OCR Space extracted {len(text)} chars from {len(all_text)} pages")
        except ImportError:
            log_map("OCR service not available for fallback")

    # Strategy 3: Raw text read (last resort)
    if not text.strip():
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            log_map(f"Raw text read: {len(text)} chars (may be garbled for binary PDFs)")
        except Exception:
            return {"error": "Could not extract text from PDF"}

    questions = parse_model_answer_text_regex(text)
    question_structure = list(questions.keys())
    total_marks = sum(q.get("marks", 0) for q in questions.values())

    return {
        "questions": questions,
        "total_marks": total_marks,
        "question_structure": question_structure,
        "source_type": "pdf",
        "processing_mode": "text_fallback"
    }


# ===================== CONVERSION TO LEGACY FORMAT =====================

def to_legacy_format(processed_result):
    """
    Convert the rich model answer structure to the legacy format used by
    fileConverter.js and the existing pipeline.

    Returns list of:
    [
        {
            "questionNumber": "1(a)",
            "modelAnswer": "...",
            "maxMarks": 5,
            "type": "long",
            "contentTypes": ["text", "diagram"],
            "keywords": [...],
            "diagramData": {...},
            "mathExpressions": [...]
        }
    ]
    """
    questions = processed_result.get("questions", {})
    question_structure = processed_result.get("question_structure", list(questions.keys()))

    legacy = []
    for q_num in question_structure:
        q = questions[q_num]
        legacy_q = {
            "questionNumber": q_num,
            "modelAnswer": q.get("text", ""),
            "maxMarks": q.get("marks", 0),
            "type": q.get("type", "long"),
            # New enriched fields (backward compatible — old code ignores them)
            "contentTypes": q.get("content_types", ["text"]),
            "keywords": q.get("keywords", []),
            "diagramData": q.get("diagram"),
            "mathExpressions": q.get("math_expressions", [])
        }
        legacy.append(legacy_q)

    return legacy


# ===================== ENTRY POINT =====================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Model Answer Processor — Extract structured content from model answer PDFs"
    )
    parser.add_argument("--input", required=True, help="Path to model answer PDF or TXT file")
    parser.add_argument("--output", help="Path to write output JSON (default: stdout)")
    parser.add_argument("--output-dir", help="Directory for intermediate files")
    parser.add_argument("--legacy", action="store_true",
                        help="Output in legacy format compatible with existing pipeline")
    args = parser.parse_args()

    input_path = os.path.abspath(args.input)

    if not os.path.exists(input_path):
        error = {"error": f"Input file not found: {input_path}"}
        print(json.dumps(error))
        sys.exit(1)

    log_map(f"Input: {input_path}")
    log_map(f"Gemini available: {GEMINI_AVAILABLE}")

    result = process_model_answer(input_path, args.output_dir)

    if args.legacy:
        result = to_legacy_format(result)

    output_json = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        output_path = os.path.abspath(args.output)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(output_json)
        log_map(f"Output written to: {output_path}")
    else:
        # Print to stdout for Node.js consumption
        print(output_json)
