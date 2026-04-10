"""
Enhanced OCR Pipeline
---------------------
Main orchestrator for the Hybrid OCR + Gemini AI pipeline.
Drop-in replacement for ocr_service.py with the same CLI interface
and backward-compatible JSON output.

Usage:
    python -m ocr.enhanced_ocr_pipeline --input <pdf_or_image_path> --output-dir <dir>

Pipeline Flow (PDF):
    1. Split PDF into page images
    2. First page → Gemini student info extractor (info only, NOT graded)
    3. Pages 2+ (answer pages):
       a. OCRSpace → text extraction
       b. Gemini → content classification (diagrams, graphs, etc.)
       c. Hybrid merge of both results
    4. Extract structured answers from merged text
       a. Try regex patterns first
       b. If regex fails, use Gemini to identify question boundaries
    5. Output backward-compatible JSON + new enriched fields

Output JSON (backward compatible + new fields):
{
    "full_text": "...",
    "pages": [ { "page_number": 1, "text": "..." }, ... ],
    "structured_answers": [ { "question_number": "1", "answer_text": "..." }, ... ],
    "student_info": { "name": "", "roll_number": "", ... },
    "content_analysis": [ { "page": 1, "content_blocks": [...] } ],
    "pipeline_mode": "hybrid"
}
"""

import os
import sys
import json
import time
import re
import argparse

# --------------- Path Setup ---------------
# Add the python/ directory to sys.path so we can import ocr_service
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_DIR = os.path.dirname(SCRIPT_DIR)
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)

# --------------- Load Environment ---------------
from dotenv import load_dotenv
load_dotenv(os.path.join(PYTHON_DIR, '.env'))

# --------------- Import existing OCR service functions ---------------
# We reuse the proven OCR functions without modifying the original file
from ocr_service import (
    pdf_to_images,
    run_ocr,
    run_ocr_pdf_direct,
    extract_questions,
    is_handwritten_page,
    log as ocr_log
)

# --------------- Import new Gemini modules ---------------
from ocr.gemini_client import log, GEMINI_AVAILABLE, gemini_analyze_image, ai_correct_ocr_text
from ocr.gemini_first_page_extractor import extract_student_info
from ocr.content_classifier import classify_page_content, get_content_type_summary
from ocr.hybrid_extractor import merge_page_results, merge_all_pages


def log_pipeline(msg):
    """Log with pipeline prefix."""
    print(f"[Enhanced Pipeline] {msg}", file=sys.stderr, flush=True)


# ===================== GEMINI QUESTION EXTRACTOR =====================
QUESTION_EXTRACTION_PROMPT = """You are analyzing OCR text from a student's handwritten answer sheet.
The OCR was imperfect and may have garbled question numbers or split them across lines.

Your task: Identify each distinct question/answer in this text and assign the correct question number.

The model answer questions are in format like: Q1(a), Q1(b), Q2(a), Q2(b), Q2(c), Q3(a), Q3(b)
OR simple format: Q1, Q2, Q3

Look for patterns like:
- "Ans (a)" or "Ans(a)" or "Ans 1" at the start of answers
- "(a)", "(b)", "(c)" markers that indicate sub-questions
- Question numbers like "1", "2", "3" near "Ans" markers
- Page number indicators that hint at question boundaries

Given the OCR text below, return a JSON array of structured answers:
[
    {"question_number": "1(a)", "answer_text": "the actual answer text..."},
    {"question_number": "1(b)", "answer_text": "the actual answer text..."}
]

IMPORTANT: 
- Use the question numbering format that matches common exam patterns (e.g., "1(a)", "2(b)")
- Include ALL the answer text for each question
- Remove page headers, page numbers, and noise from the answer text
- If you can't determine the exact question number, use your best guess based on context

OCR TEXT:
"""


def gemini_extract_questions(full_text, model_answer_format=None):
    """
    Use Gemini to identify question boundaries when regex-based extraction fails.
    This handles garbled OCR where question markers are split across lines.
    
    Args:
        full_text (str): The full OCR text from all answer pages.
        model_answer_format (str): Hint about expected question format.
    
    Returns:
        list: Structured answers list, or empty list on failure.
    """
    if not GEMINI_AVAILABLE:
        return []
    
    prompt = QUESTION_EXTRACTION_PROMPT + full_text[:8000]  # Limit to avoid token limits
    
    if model_answer_format:
        prompt += f"\n\nHINT: The expected question format is: {model_answer_format}"
    
    log("Using Gemini to extract question boundaries from OCR text...")
    
    # Use text-only Gemini call
    from ocr.gemini_client import gemini_analyze_text
    response = gemini_analyze_text(prompt)
    
    if not response:
        log("Gemini question extraction returned no response")
        return []
    
    # Parse JSON response
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    
    try:
        parsed = json.loads(cleaned)
        if not isinstance(parsed, list):
            log("Gemini returned non-array response for question extraction")
            return []
        
        results = []
        for item in parsed:
            if isinstance(item, dict) and "question_number" in item:
                results.append({
                    "question_number": str(item["question_number"]),
                    "subtype": "",
                    "question_text": "",
                    "answer_text": str(item.get("answer_text", "")).strip()
                })
        
        log(f"Gemini extracted {len(results)} questions: "
            f"Q{', Q'.join(r['question_number'] for r in results)}")
        return results
    
    except json.JSONDecodeError as e:
        log(f"Failed to parse Gemini question extraction response: {e}")
        return []


def _normalize_ocr_text(text):
    """
    Pre-process OCR text to fix common issues where question markers
    are split across multiple lines by OCR.
    
    Examples of what this fixes:
        "Ans\n=\n(a)\n" → "Ans (a) "
        "Ans\n*\n(b)\n" → "Ans (b) "  
        "Am (9\n3\n"   → "Ans (a)\n3\n"
        "(b)\nAns\n"   → "Ans (b)\n"
    """
    # Fix garbled "Am (9" → "Ans (a)" (common OCR error for handwritten "Ans (a)")
    normalized = re.sub(r'\bAm\s*\(\d', 'Ans (a)', text, flags=re.IGNORECASE)
    
    # Join "Ans" with following sub-question marker on next line(s)
    # Handles: "Ans\n=\n(a)" → "Ans (a)"
    normalized = re.sub(
        r'(Ans|Am|ans)\s*\n\s*[=*i%\s]*\n?\s*(\([a-c]\))',
        r'Ans \2',
        normalized, flags=re.IGNORECASE
    )
    # Also handle "Ans\n(a)" directly  
    normalized = re.sub(
        r'(Ans|Am|ans)\s*\n\s*(\([a-c]\))',
        r'Ans \2',
        normalized, flags=re.IGNORECASE
    )
    # Handle reversed pattern: "(b)\nAns" or "(c)\nAns" → "Ans (b)" / "Ans (c)"
    normalized = re.sub(
        r'(\([a-c]\))\s*\n\s*(Ans|Am|ans)',
        r'Ans \1',
        normalized, flags=re.IGNORECASE
    )
    # Handle standalone (a)/(b)/(c) at line start with no Ans marker
    # Common on continuation pages of answer sheets
    normalized = re.sub(
        r'(?:^|\n)\s*(\([a-c]\))\s*\n',
        r'\nAns \1\n',
        normalized
    )
    return normalized


# Sub-question regex: matches patterns like "Ans (a)", "Ans (b)", "Ans (c)"
SUB_QUESTION_PATTERN = re.compile(
    r'(?:^|\n)\s*(?:Ans|Am|ans)\s*\(([a-c])\)',
    re.IGNORECASE | re.MULTILINE
)

# Main question number regex: matches "Q1", "Q2", "Q3" or bare "1", "2", "3" with separator
MAIN_QUESTION_PATTERN = re.compile(
    r'(?:^|\n)\s*(?:Q|q)?\s*(\d+)\s*[.):;\n]\s*(?:\d+\s*)?(?:Ans|Am|ans)',
    re.IGNORECASE | re.MULTILINE
)


def _extract_with_subquestions(text):
    """
    Extract answers using sub-question patterns like Ans (a), Ans (b).
    Infers main question numbers by tracking (a) resets:
    - Each time (a) appears, it starts a new main question
    - (b), (c) continue the current main question
    """
    # Find all sub-question markers
    sub_matches = list(SUB_QUESTION_PATTERN.finditer(text))
    
    if not sub_matches:
        return []
    
    log_pipeline(f"Found {len(sub_matches)} sub-question markers: "
                f"{[m.group(1) for m in sub_matches]}")
    
    results = []
    current_main_q = 0  # Will be incremented to 1 on first (a)
    last_letter = None
    
    for i, match in enumerate(sub_matches):
        sub_letter = match.group(1)  # 'a', 'b', or 'c'
        
        # When we see (a), start a new main question
        if sub_letter == 'a':
            current_main_q += 1
        elif sub_letter == 'b' and last_letter == 'b':
            # Duplicate (b) — this is a false positive from mid-page sub-heading
            # Skip this but keep the text as continuation of previous answer
            if results:
                # Find next marker to determine text range
                start_pos = match.end()
                end_pos = sub_matches[i + 1].start() if i + 1 < len(sub_matches) else len(text)
                extra_text = text[start_pos:end_pos].strip()
                extra_text = re.sub(r'^[\s=*\xA1i%\n]+', '', extra_text)
                results[-1]["answer_text"] += "\n" + extra_text
            last_letter = sub_letter
            continue
        
        # Extract text from this marker to the next
        start_pos = match.end()
        end_pos = sub_matches[i + 1].start() if i + 1 < len(sub_matches) else len(text)
        answer_text = text[start_pos:end_pos].strip()
        
        # Clean up noise characters from OCR
        answer_text = re.sub(r'^[\s=*\xA1i%\n]+', '', answer_text)
        
        q_number = f"{current_main_q}({sub_letter})"
        
        results.append({
            "question_number": q_number,
            "subtype": "",
            "question_text": "",
            "answer_text": answer_text
        })
        last_letter = sub_letter
    
    if results:
        log_pipeline(f"Sub-question extraction found {len(results)} answers: "
                    f"Q{', Q'.join(r['question_number'] for r in results)}")
    
    return results


def enhanced_extract_questions(full_text):
    """
    Enhanced question extraction that tries multiple strategies:
    1. Standard regex patterns (from ocr_service.py)
    2. Normalized text + sub-question regex (handles OCR-garbled Q markers)
    3. Gemini AI question extraction (most powerful, uses quota)
    4. Fallback to full text as Q1 if everything fails
    """
    # Strategy 1: Standard regex extraction
    structured = extract_questions(full_text)
    
    # If regex found multiple questions, great — use them
    if len(structured) > 1:
        log_pipeline(f"Regex extracted {len(structured)} answers — using regex results")
        return structured
    
    # Strategy 2: Normalize text and try sub-question extraction
    normalized = _normalize_ocr_text(full_text)
    sub_q_results = _extract_with_subquestions(normalized)
    
    if len(sub_q_results) > 1:
        log_pipeline(f"Sub-question extraction found {len(sub_q_results)} answers — using those")
        return sub_q_results
    
    # Strategy 3: If still 1 answer (or 0), try Gemini
    if GEMINI_AVAILABLE and len(full_text) > 200:
        log_pipeline("Local extraction found ≤1 answer — trying Gemini question extraction...")
        gemini_answers = gemini_extract_questions(full_text)
        
        if len(gemini_answers) > 1:
            log_pipeline(f"Gemini found {len(gemini_answers)} answers — using Gemini results")
            return gemini_answers
    
    # Strategy 4: Fallback — return whatever regex found (or full text as Q1)
    log_pipeline(f"All extraction strategies exhausted — using fallback: {len(structured)} answer(s)")
    return structured


# ===================== SINGLE IMAGE PROCESSING =====================
def process_image_file(image_path, out_dir):
    """
    Process a single image file through the enhanced pipeline.
    """
    os.makedirs(out_dir, exist_ok=True)
    log_pipeline(f"Processing image: {image_path}")

    # --- OCRSpace extraction ---
    ocr_text = run_ocr(image_path)

    # --- Gemini classification (if available) ---
    classification = {"page_number": 1, "content_blocks": []}
    if GEMINI_AVAILABLE:
        try:
            classification = classify_page_content(image_path, page_number=1)
        except Exception as e:
            log_pipeline(f"Gemini classification failed, using OCR only: {e}")

    # --- Merge results ---
    merged = merge_page_results(ocr_text, classification, page_number=1)

    # --- Extract structured answers ---
    best_text = merged.get("merged_text", ocr_text or "")
    structured = enhanced_extract_questions(best_text)

    # --- Attempt student info extraction from single image ---
    student_info = {"name": "", "roll_number": "", "exam_date": "", "branch": "", "paper_code": ""}
    if GEMINI_AVAILABLE:
        try:
            student_info = extract_student_info(image_path)
        except Exception as e:
            log_pipeline(f"Student info extraction failed: {e}")

    # --- Build result (backward compatible) ---
    result = {
        "full_text": best_text,
        "pages": [{"page_number": 1, "text": best_text}],
        "structured_answers": structured,
        # New enhanced fields
        "student_info": student_info,
        "content_analysis": [classification],
        "pipeline_mode": "hybrid" if GEMINI_AVAILABLE else "ocr_only"
    }

    if not best_text:
        result["warning"] = "Both OCR and Gemini returned empty text."

    return result


# ===================== PDF PROCESSING =====================
def process_pdf_file(pdf_path, out_dir):
    """
    Process a PDF file through the enhanced hybrid pipeline.
    
    KEY CHANGE: Page 1 is the cover page (student info only).
    Only pages 2+ contain actual answers and are included in grading text.
    """
    os.makedirs(out_dir, exist_ok=True)
    log_pipeline(f"Processing PDF: {pdf_path}")

    # --- Step 1: Convert PDF to images ---
    try:
        images = pdf_to_images(pdf_path, out_dir)
        log_pipeline(f"PDF converted to {len(images)} page images")
    except (ImportError, Exception) as e:
        log_pipeline(f"PDF to image conversion failed: {e}")
        log_pipeline("Falling back to direct PDF OCR (no Gemini enhancement)...")
        return _fallback_pdf_direct(pdf_path, out_dir)

    if not images:
        return {
            "full_text": "",
            "pages": [],
            "structured_answers": [],
            "student_info": {},
            "content_analysis": [],
            "pipeline_mode": "failed",
            "warning": "No pages extracted from PDF"
        }

    # --- Step 2: First page → student info extraction ONLY ---
    # The first page is the cover/info page and should NOT be included in grading
    student_info = {"name": "", "roll_number": "", "exam_date": "", "branch": "", "paper_code": ""}
    first_page_text = ""
    
    if GEMINI_AVAILABLE:
        try:
            log_pipeline("Step 2: Extracting student info from first page (info only, not graded)...")
            student_info = extract_student_info(images[0])
            log_pipeline(f"Student: {student_info.get('name', 'N/A')}, "
                        f"Roll: {student_info.get('roll_number', 'N/A')}")
        except Exception as e:
            log_pipeline(f"First page extraction failed (non-fatal): {e}")
    
    # Also OCR the first page just to store it, but don't include in grading text
    first_page_text = run_ocr(images[0])
    time.sleep(1)

    # Brief pause after first Gemini call to respect rate limits
    if GEMINI_AVAILABLE:
        time.sleep(1)

    # --- Step 3: Process ANSWER pages only (page 2+) ---
    # Page 1 is cover page — skip it for grading
    answer_start_page = 1  # 0-indexed, so page 2 in human terms
    if len(images) <= 1:
        # Single page PDF: include everything
        answer_start_page = 0
        log_pipeline("Single page PDF — including page 1 in grading")
    else:
        log_pipeline(f"Step 3: Processing answer pages (2-{len(images)})...")
        log_pipeline("Page 1 is cover page — excluded from grading text")

    all_pages = []           # Backward-compatible page list (includes ALL pages)
    page_merge_results = []  # Enhanced per-page results (answer pages only)
    content_analysis = []    # Content classification per page

    # Store first page info (for reference, not grading)
    all_pages.append({
        "page_number": 1,
        "text": first_page_text,
        "is_cover_page": True
    })

    for idx in range(answer_start_page, len(images)):
        img_path = images[idx]
        page_num = idx + 1
        log_pipeline(f"Page {page_num}/{len(images)}: {os.path.basename(img_path)}")

        # --- 3a: OCRSpace text extraction ---
        ocr_text = run_ocr(img_path)
        time.sleep(1)  # Rate limit for free OCR API

        # --- 3b: Gemini content classification ---
        classification = {"page_number": page_num, "content_blocks": []}
        if GEMINI_AVAILABLE:
            try:
                classification = classify_page_content(img_path, page_number=page_num)
            except Exception as e:
                log_pipeline(f"Page {page_num} Gemini classification failed: {e}")
            time.sleep(1)  # Rate limit for Gemini

        # --- 3c: Hybrid merge ---
        merged = merge_page_results(ocr_text, classification, page_number=page_num)

        # Store results
        all_pages.append({
            "page_number": page_num,
            "text": merged.get("merged_text", ocr_text or "")
        })
        page_merge_results.append(merged)
        content_analysis.append(classification)

    # --- Step 4: Build full text and extract structured answers ---
    # ONLY use text from answer pages (not the cover page)
    log_pipeline("Step 4: Extracting structured answers from answer pages...")
    document_merge = merge_all_pages(page_merge_results)
    full_text = document_merge.get("full_text", "")
    
    if GEMINI_AVAILABLE and full_text.strip():
        try:
            log_pipeline("Step 4.5: AI-assisted OCR semantic error correction...")
            corrected_text = ai_correct_ocr_text(full_text)
            full_text = corrected_text
            document_merge["full_text"] = full_text
        except Exception as e:
            log_pipeline(f"OCR correction failed (using original text): {e}")

    log_pipeline(f"Answer text: {len(full_text)} chars (excluding cover page)")

    # Use enhanced extraction (regex first, then Gemini fallback)
    structured_answers = enhanced_extract_questions(full_text)
    log_pipeline(f"Extracted {len(structured_answers)} structured answer(s)")

    # --- Build final result ---
    pipeline_mode = "hybrid" if GEMINI_AVAILABLE else "ocr_only"

    result = {
        # Backward-compatible fields (same as ocr_service.py)
        "full_text": full_text,
        "pages": all_pages,
        "structured_answers": structured_answers,
        # New enhanced fields
        "student_info": student_info,
        "content_analysis": content_analysis,
        "pipeline_mode": pipeline_mode,
        "extraction_sources": document_merge.get("extraction_sources", []),
        "has_visual_content": document_merge.get("has_visual_content", False),
        "cover_page_excluded": len(images) > 1  # Flag indicating cover page was excluded
    }

    if not full_text.strip():
        result["warning"] = "Pipeline returned empty text for all pages."

    log_pipeline(f"Pipeline complete: {len(all_pages)} pages ({len(page_merge_results)} answer pages), "
                f"{len(structured_answers)} answers, mode={pipeline_mode}")

    return result


def _fallback_pdf_direct(pdf_path, out_dir):
    """
    Fallback: send PDF directly to OCR API when image conversion fails.
    Returns backward-compatible result.
    """
    full_text, pages = run_ocr_pdf_direct(pdf_path)

    if not full_text:
        return {
            "full_text": "",
            "pages": pages,
            "structured_answers": [],
            "student_info": {},
            "content_analysis": [],
            "pipeline_mode": "fallback_ocr",
            "warning": "PDF direct OCR returned empty text."
        }

    structured = enhanced_extract_questions(full_text)
    return {
        "full_text": full_text,
        "pages": pages,
        "structured_answers": structured,
        "student_info": {},
        "content_analysis": [],
        "pipeline_mode": "fallback_ocr"
    }


# ===================== MODEL ANSWER PROCESSING MODE =====================

def process_model_answer_mode(input_path, out_dir, legacy=False):
    """
    Process a model answer file and output structured JSON.
    Called when --mode model-answer is used.
    """
    from ocr.model_answer_processor import process_model_answer, to_legacy_format

    log_pipeline(f"Mode: MODEL ANSWER PROCESSING")
    result = process_model_answer(input_path, out_dir)

    if legacy:
        result = to_legacy_format(result)

    return result


# ===================== SEGMENTATION MODE =====================

def process_segmentation_mode(student_ocr_json_path, model_structure_json_path):
    """
    Run segmentation + alignment on student OCR results using model structure.
    Called when --mode segment is used.
    """
    from ocr.segmentation_engine import segment_student_answers
    from ocr.alignment_engine import align_answers, to_grading_input

    log_pipeline(f"Mode: SEGMENTATION + ALIGNMENT")

    # Load student OCR result
    with open(student_ocr_json_path, 'r', encoding='utf-8') as f:
        student_ocr = json.load(f)

    # Load model structure
    with open(model_structure_json_path, 'r', encoding='utf-8') as f:
        model_structure = json.load(f)

    student_text = student_ocr.get("full_text", "")
    student_structured = student_ocr.get("structured_answers", [])

    # Step 1: Segment
    segments = segment_student_answers(
        student_text=student_text,
        model_structure=model_structure,
        student_structured=student_structured
    )

    # Step 2: Align
    alignment = align_answers(segments, model_structure)

    # Step 3: Convert to grading input format
    grading_input = to_grading_input(alignment)

    log_pipeline(f"Segmentation complete: {alignment['summary']['matched_questions']}/"
                 f"{alignment['summary']['total_questions']} questions matched, "
                 f"confidence={alignment['summary']['overall_confidence']:.3f}")

    return {
        "segments": segments,
        "alignment": alignment,
        "grading_input": grading_input
    }


# ===================== ENTRY POINT =====================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Enhanced OCR Pipeline — Hybrid OCR + Gemini AI"
    )
    parser.add_argument("--input", required=True, help="Path to PDF or image file")
    parser.add_argument("--output-dir", required=True, help="Directory for output files")
    parser.add_argument("--mode", default="ocr",
                        choices=["ocr", "model-answer", "segment"],
                        help="Processing mode: ocr (default), model-answer, segment")
    parser.add_argument("--model-structure", default=None,
                        help="Path to model structure JSON (required for segment mode)")
    parser.add_argument("--legacy", action="store_true",
                        help="Output in legacy format (for model-answer mode)")
    args = parser.parse_args()

    input_path = os.path.abspath(args.input)
    out_dir = os.path.abspath(args.output_dir)
    ext = os.path.splitext(input_path)[1].lower()

    log_pipeline(f"Input: {input_path}")
    log_pipeline(f"Output dir: {out_dir}")
    log_pipeline(f"Mode: {args.mode}")
    log_pipeline(f"File type: {ext}")
    log_pipeline(f"Gemini available: {GEMINI_AVAILABLE}")
    log_pipeline(f"File exists: {os.path.exists(input_path)}")

    if not os.path.exists(input_path):
        error_result = {"error": f"Input file not found: {input_path}"}
        print(json.dumps(error_result), file=sys.stdout)
        sys.exit(1)

    file_size = os.path.getsize(input_path)
    log_pipeline(f"File size: {file_size} bytes ({file_size / 1024:.1f} KB)")

    try:
        # ---- MODE: Model Answer Processing ----
        if args.mode == "model-answer":
            result = process_model_answer_mode(input_path, out_dir, legacy=args.legacy)

        # ---- MODE: Segmentation + Alignment ----
        elif args.mode == "segment":
            if not args.model_structure:
                result = {"error": "--model-structure is required for segment mode"}
            elif not os.path.exists(args.model_structure):
                result = {"error": f"Model structure file not found: {args.model_structure}"}
            else:
                result = process_segmentation_mode(input_path, args.model_structure)

        # ---- MODE: Student OCR (default, existing behavior) ----
        else:
            if ext == ".pdf":
                result = process_pdf_file(input_path, out_dir)
            elif ext in [".jpg", ".jpeg", ".png", ".bmp", ".tiff"]:
                result = process_image_file(input_path, out_dir)
            else:
                result = {"error": f"Unsupported file type: {ext}"}

        # Write result JSON to file
        result_path = os.path.join(out_dir, "ocr_result.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        log_pipeline(f"Result written to: {result_path}")

        # Summary (for OCR mode)
        if "error" not in result and args.mode == "ocr":
            log_pipeline(f"Full text: {len(result.get('full_text', ''))} chars")
            log_pipeline(f"Answers: {len(result.get('structured_answers', []))}")
            log_pipeline(f"Student: {result.get('student_info', {}).get('name', 'N/A')}")
            log_pipeline(f"Mode: {result.get('pipeline_mode', 'unknown')}")
            if result.get('cover_page_excluded'):
                log_pipeline("Cover page: EXCLUDED from grading")
            for sa in result.get("structured_answers", []):
                log_pipeline(f"  Q{sa['question_number']}: {len(sa['answer_text'])} chars")

        # Print JSON to stdout for Node.js consumption
        print(json.dumps(result, ensure_ascii=False))

    except Exception as e:
        log_pipeline(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)
        error_result = {"error": str(e)}
        print(json.dumps(error_result), file=sys.stdout)
        sys.exit(1)
