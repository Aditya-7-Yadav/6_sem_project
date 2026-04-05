"""
OCR Service Wrapper
-------------------
Standalone script that replicates the Stud_ans_sheet_OCR.ipynb pipeline
for server-side integration. The original notebook is NOT modified.

Usage:
    python ocr_service.py --input <pdf_or_image_path> --output-dir <output_directory>

Output:
    Writes a JSON file to <output_directory>/ocr_result.json with structure:
    {
        "full_text": "...",
        "pages": [ { "page_number": 1, "text": "..." }, ... ],
        "structured_answers": [ { "question_number": "1", "answer_text": "..." }, ... ]
    }
"""

import os
import sys
import json
import time
import re
import argparse
import requests

try:
    from pdf2image import convert_from_path
except ImportError:
    convert_from_path = None

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

# ===================== CONFIG =====================
API_KEY = os.environ.get("OCR_API_KEY", "K86291774288957")

OCR_PAYLOAD = {
    "apikey": API_KEY,
    "language": "eng",
    "ocrengine": 2,
    "scale": True,
    "detectOrientation": True
}


def log(msg):
    """Log to stderr so Node.js can capture it without polluting stdout JSON."""
    print(f"[OCR] {msg}", file=sys.stderr, flush=True)


# ===================== PDF → IMAGES =====================
def pdf_to_images(pdf_path, out_dir, dpi=200):
    os.makedirs(out_dir, exist_ok=True)
    if convert_from_path is None:
        raise ImportError("pdf2image is not installed. Run: pip install pdf2image")
    log(f"Converting PDF to images (dpi={dpi})...")
    pages = convert_from_path(pdf_path, dpi=dpi)
    image_paths = []
    for i, page in enumerate(pages, start=1):
        img_path = os.path.join(out_dir, f"page_{i}.jpg")
        page = page.convert("L")  # grayscale
        page.save(img_path, "JPEG", quality=85)
        image_paths.append(img_path)
        log(f"  Saved page {i} -> {img_path}")
    log(f"PDF converted: {len(image_paths)} page(s)")
    return image_paths


# ===================== HANDWRITING DETECTION =====================
def is_handwritten_page(img_path):
    if cv2 is None:
        return True  # default to treating as handwritten if cv2 is missing
    img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return True
    edges = cv2.Canny(img, 50, 150)
    edge_ratio = np.sum(edges > 0) / edges.size
    return edge_ratio > 0.015


def find_first_answer_page(image_paths):
    for idx, img in enumerate(image_paths):
        if is_handwritten_page(img):
            return idx + 1  # 1-based
    return 1  # fallback: start from page 1


# ===================== OCR =====================
def run_ocr(img_path, retries=3):
    """Run OCR on a single image file via ocr.space API."""
    log(f"Running OCR on: {img_path}")
    for attempt in range(retries):
        try:
            with open(img_path, "rb") as f:
                r = requests.post(
                    "https://api.ocr.space/parse/image",
                    files={"file": f},
                    data=OCR_PAYLOAD,
                    timeout=90
                )
            data = r.json()
            log(f"  API response status: {r.status_code}, errored: {data.get('IsErroredOnProcessing')}")

            if data.get("IsErroredOnProcessing"):
                err_msg = data.get("ErrorMessage", ["Unknown"])[0] if isinstance(data.get("ErrorMessage"), list) else data.get("ErrorMessage", "Unknown")
                log(f"  OCR API error: {err_msg}")
                if attempt < retries - 1:
                    time.sleep(5)
                    continue
                return ""

            parsed = data.get("ParsedResults", [])
            if parsed:
                text = parsed[0].get("ParsedText", "").strip()
                log(f"  OCR extracted {len(text)} chars")
                if text:
                    return text
                else:
                    log("  WARNING: OCR returned empty text")
            else:
                log("  WARNING: No ParsedResults in response")

        except Exception as e:
            log(f"  OCR attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(5)
    return ""


def run_ocr_pdf_direct(pdf_path, retries=3):
    """Send PDF directly to ocr.space API (no image conversion needed)."""
    log(f"Sending PDF directly to OCR API: {pdf_path}")
    for attempt in range(retries):
        try:
            with open(pdf_path, "rb") as f:
                r = requests.post(
                    "https://api.ocr.space/parse/image",
                    files={"file": (os.path.basename(pdf_path), f, "application/pdf")},
                    data=OCR_PAYLOAD,
                    timeout=120
                )
            data = r.json()
            log(f"  API response status: {r.status_code}")

            if data.get("IsErroredOnProcessing"):
                err_msg = data.get("ErrorMessage", "Unknown")
                log(f"  OCR API error (PDF direct): {err_msg}")
                if attempt < retries - 1:
                    time.sleep(5)
                    continue
                return "", []

            parsed_results = data.get("ParsedResults", [])
            pages = []
            full_text_parts = []

            for idx, pr in enumerate(parsed_results, start=1):
                text = pr.get("ParsedText", "").strip()
                pages.append({"page_number": idx, "text": text})
                full_text_parts.append(text)
                log(f"  Page {idx}: {len(text)} chars")

            full_text = "\n".join(full_text_parts)
            return full_text, pages

        except Exception as e:
            log(f"  PDF direct OCR attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(5)

    return "", []


# ===================== STUDENT ANSWER PARSER =====================
# This is the KEY fix: detect how students write answers and extract them
# by question number. Students may write in any of these formats:
#   Q1 Ans: ..., Q1. Ans ..., q1 ans ..., Q1) ...
#   Answer 1: ..., answer 1. ...
#   Ans1: ..., Ans 1 ..., ans1. ...
#   A1. ..., A1: ...
#   1. Ans ..., 1) ...
#   Just "1." or "1)" at the start of a line

# The critical insight: we match answers by question NUMBER, not by sequence.
# Students may skip questions or answer them out of order.

ANSWER_HEADER_PATTERN = re.compile(
    r'''
    (?:^|\n)                          # start of text or newline
    \s*                               # optional whitespace
    (?:
        # Pattern 1: Q<num> variants — Q1, Q.1, Q1., Q1), Q1:, Q 1, q1 ans, Q1 Ans:
        (?:[Qq]\s*\.?\s*(\d+)\s*[.):;]?\s*(?:[Aa]ns(?:wer)?)?[.):;\s]*)
        |
        # Pattern 2: Answer <num> variants — Answer 1, answer 1:, ANSWER 1.
        (?:[Aa](?:ns(?:wer)?)\s*(\d+)\s*[.):;\s]*)
        |
        # Pattern 3: Ans<num> variants — Ans1, Ans 1, ans1:, ANS1.
        (?:[Aa]ns\s*(\d+)\s*[.):;\s]*)
        |
        # Pattern 4: A<num> at start — A1., A1:, A1), a1
        (?:[Aa]\s*(\d+)\s*[.):;\s]+)
        |
        # Pattern 5: bare number — 1., 1), 1:, 1 - at line start
        (?:(\d+)\s*[.):][\s]*)
    )
    ''',
    re.VERBOSE | re.MULTILINE
)


def extract_questions(text):
    """
    Splits OCR text into question-answer blocks.
    Detects student answer patterns and maps by question number.
    Returns answers keyed by question number (handles out-of-sequence).
    """
    if not text or not text.strip():
        log("  extract_questions: empty text, returning empty list")
        return []

    log(f"  extract_questions: parsing {len(text)} chars of text")

    matches = list(ANSWER_HEADER_PATTERN.finditer(text))

    if not matches:
        log("  extract_questions: no answer headers detected, treating entire text as Q1")
        # If no patterns found, return the whole text as a single answer for Q1
        return [{
            "question_number": "1",
            "subtype": "",
            "question_text": "",
            "answer_text": text.strip()
        }]

    log(f"  extract_questions: found {len(matches)} answer header(s)")

    results = []
    seen_questions = set()

    for i, match in enumerate(matches):
        # Extract question number from whichever group matched
        qnum = None
        for g in range(1, 6):
            if match.group(g):
                qnum = match.group(g)
                break

        if not qnum:
            continue

        # Determine the answer text (from end of header to start of next header)
        start_pos = match.end()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        answer_text = text[start_pos:end_pos].strip()

        # Skip duplicate question numbers (keep first occurrence)
        if qnum in seen_questions:
            # Append to existing answer if same question appears again
            for r in results:
                if r["question_number"] == qnum:
                    r["answer_text"] += "\n" + answer_text
                    break
            continue

        seen_questions.add(qnum)

        results.append({
            "question_number": qnum,
            "subtype": "",
            "question_text": "",
            "answer_text": answer_text
        })

    log(f"  extract_questions: extracted {len(results)} answer(s): Q{', Q'.join(r['question_number'] for r in results)}")
    return results


# ===================== IMAGE FILE OCR =====================
def ocr_image_file(image_path, out_dir):
    """Handle a single image file (JPG/PNG)"""
    os.makedirs(out_dir, exist_ok=True)
    log(f"Processing image file: {image_path}")

    text = run_ocr(image_path)

    if not text:
        log("WARNING: OCR returned empty text for image!")
        return {
            "full_text": "",
            "pages": [{"page_number": 1, "text": ""}],
            "structured_answers": [],
            "warning": "OCR returned empty text. The image may be unclear or the API may have failed."
        }

    structured = extract_questions(text)
    return {
        "full_text": text,
        "pages": [{"page_number": 1, "text": text}],
        "structured_answers": structured
    }


# ===================== MAIN PIPELINE =====================
def ocr_pdf_pipeline(pdf_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    log(f"Processing PDF: {pdf_path}")

    # Try pdf2image conversion first
    try:
        images = pdf_to_images(pdf_path, out_dir)
    except (ImportError, Exception) as e:
        log(f"pdf2image conversion failed: {e}")
        log("Falling back to direct PDF upload to OCR API...")
        full_text, pages = run_ocr_pdf_direct(pdf_path)
        if not full_text:
            return {
                "full_text": "",
                "pages": pages,
                "structured_answers": [],
                "warning": "OCR returned empty text for PDF."
            }
        structured = extract_questions(full_text)
        return {
            "full_text": full_text,
            "pages": pages,
            "structured_answers": structured
        }

    start_page = find_first_answer_page(images)
    log(f"First answer page: {start_page}")

    all_pages = []
    full_text_parts = []

    for page_num in range(start_page, len(images) + 1):
        img = images[page_num - 1]
        log(f"OCR page {page_num}/{len(images)}")

        text = run_ocr(img)

        all_pages.append({
            "page_number": page_num,
            "text": text
        })
        full_text_parts.append(text)
        time.sleep(2)  # rate limit for free API

    full_text = "\n".join(full_text_parts)

    if not full_text.strip():
        log("WARNING: OCR returned empty text for all pages!")
        return {
            "full_text": "",
            "pages": all_pages,
            "structured_answers": [],
            "warning": "OCR returned empty text for all pages."
        }

    structured_answers = extract_questions(full_text)

    return {
        "full_text": full_text,
        "pages": all_pages,
        "structured_answers": structured_answers
    }


# ===================== ENTRY POINT =====================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OCR Service for answer sheets")
    parser.add_argument("--input", required=True, help="Path to PDF or image file")
    parser.add_argument("--output-dir", required=True, help="Directory for output files")
    args = parser.parse_args()

    input_path = os.path.abspath(args.input)
    out_dir = os.path.abspath(args.output_dir)
    ext = os.path.splitext(input_path)[1].lower()

    log(f"Input file: {input_path}")
    log(f"Output dir: {out_dir}")
    log(f"File extension: {ext}")
    log(f"File exists: {os.path.exists(input_path)}")

    if not os.path.exists(input_path):
        error_result = {"error": f"Input file not found: {input_path}"}
        print(json.dumps(error_result), file=sys.stdout)
        sys.exit(1)

    file_size = os.path.getsize(input_path)
    log(f"File size: {file_size} bytes ({file_size / 1024:.1f} KB)")

    try:
        if ext == ".pdf":
            result = ocr_pdf_pipeline(input_path, out_dir)
        elif ext in [".jpg", ".jpeg", ".png", ".bmp", ".tiff"]:
            result = ocr_image_file(input_path, out_dir)
        else:
            result = {"error": f"Unsupported file type: {ext}"}

        # Write result JSON
        result_path = os.path.join(out_dir, "ocr_result.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        log(f"Result written to: {result_path}")

        # Summary logging
        if "error" not in result:
            log(f"Full text length: {len(result.get('full_text', ''))}")
            log(f"Structured answers: {len(result.get('structured_answers', []))}")
            for sa in result.get("structured_answers", []):
                log(f"  Q{sa['question_number']}: {len(sa['answer_text'])} chars")

        # Print to stdout for Node.js to consume
        print(json.dumps(result, ensure_ascii=False))

    except Exception as e:
        log(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)
        error_result = {"error": str(e)}
        print(json.dumps(error_result), file=sys.stdout)
        sys.exit(1)
