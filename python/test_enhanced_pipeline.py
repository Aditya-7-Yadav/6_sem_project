#!/usr/bin/env python3
"""
Test Script for Enhanced OCR Pipeline
--------------------------------------
Verifies that all modules import correctly, Gemini API connectivity works,
and the pipeline produces valid output.

Usage:
    cd python/
    python test_enhanced_pipeline.py

    # Or test with a real file:
    python test_enhanced_pipeline.py --input /path/to/answer_sheet.pdf
"""

import os
import sys
import json
import traceback

# Add python/ to path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# Load environment
from dotenv import load_dotenv
load_dotenv(os.path.join(SCRIPT_DIR, '.env'))

# ===================== COLOR HELPERS =====================
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


def ok(msg):
    print(f"  {GREEN}✓ PASS{RESET}: {msg}")

def fail(msg):
    print(f"  {RED}✗ FAIL{RESET}: {msg}")

def info(msg):
    print(f"  {CYAN}ℹ INFO{RESET}: {msg}")

def warn(msg):
    print(f"  {YELLOW}⚠ WARN{RESET}: {msg}")


# ===================== TEST 1: Module Imports =====================
def test_imports():
    print(f"\n{BOLD}Test 1: Module Imports{RESET}")
    all_passed = True

    modules = [
        ("ocr.gemini_client", "Gemini client"),
        ("ocr.gemini_first_page_extractor", "First page extractor"),
        ("ocr.content_classifier", "Content classifier"),
        ("ocr.hybrid_extractor", "Hybrid extractor"),
        ("ocr.gemini_evaluator", "Gemini evaluator"),
        ("ocr.enhanced_ocr_pipeline", "Enhanced pipeline"),
    ]

    for module_name, display_name in modules:
        try:
            __import__(module_name)
            ok(f"{display_name} ({module_name})")
        except Exception as e:
            fail(f"{display_name} ({module_name}): {e}")
            all_passed = False

    return all_passed


# ===================== TEST 2: Environment & API Keys =====================
def test_environment():
    print(f"\n{BOLD}Test 2: Environment & API Keys{RESET}")
    all_passed = True

    # Check .env file exists
    env_path = os.path.join(SCRIPT_DIR, '.env')
    if os.path.exists(env_path):
        ok(f".env file found at {env_path}")
    else:
        fail(f".env file not found at {env_path}")
        warn("Create python/.env with GEMINI_API_KEY and OCR_API_KEY")
        all_passed = False

    # Check GEMINI_API_KEY
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_key:
        ok(f"GEMINI_API_KEY is set ({len(gemini_key)} chars, starts with '{gemini_key[:8]}...')")
    else:
        fail("GEMINI_API_KEY not set")
        all_passed = False

    # Check OCR_API_KEY
    ocr_key = os.environ.get("OCR_API_KEY", "")
    if ocr_key:
        ok(f"OCR_API_KEY is set ({len(ocr_key)} chars)")
    else:
        warn("OCR_API_KEY not set (will use hardcoded default in ocr_service.py)")

    return all_passed


# ===================== TEST 3: Gemini API Connectivity =====================
def test_gemini_connectivity():
    print(f"\n{BOLD}Test 3: Gemini API Connectivity{RESET}")

    try:
        from ocr.gemini_client import get_gemini_client, gemini_analyze_text, GEMINI_AVAILABLE

        if not GEMINI_AVAILABLE:
            fail("google-generativeai package not installed")
            return False

        ok("Gemini SDK imported successfully")

        # Try to initialize client
        client = get_gemini_client()
        ok("Gemini client initialized")

        # Simple test prompt
        response = gemini_analyze_text("What is 2 + 2? Reply with just the number.", retries=1)
        if response and "4" in response:
            ok(f"Gemini API responded correctly: '{response.strip()}'")
        elif response:
            warn(f"Gemini responded but unexpected: '{response[:100]}'")
        else:
            fail("Gemini returned empty response")
            return False

        return True

    except Exception as e:
        fail(f"Gemini connectivity failed: {e}")
        traceback.print_exc()
        return False


# ===================== TEST 4: Generate Dummy Test Image =====================
def create_test_image(out_path):
    """Create a simple test image simulating an answer sheet page."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        warn("Pillow not installed, cannot create test image")
        return None

    # Create a white page
    img = Image.new('RGB', (800, 1100), color='white')
    draw = ImageDraw.Draw(img)

    # Try to use a system font, fall back to default
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except (IOError, OSError):
        font = ImageFont.load_default()
        font_small = font

    # Simulate a first page with student info
    draw.text((50, 30), "UNIVERSITY EXAMINATION", fill='black', font=font)
    draw.text((50, 70), "Name: Rahul Sharma", fill='black', font=font_small)
    draw.text((50, 100), "Roll Number: 21CSE045", fill='black', font=font_small)
    draw.text((50, 130), "Date: 15/03/2025", fill='black', font=font_small)
    draw.text((50, 160), "Branch: Computer Science (CSE)", fill='black', font=font_small)
    draw.text((50, 190), "Subject Code: CS-401", fill='black', font=font_small)

    # Add some answer text
    draw.text((50, 250), "Q1. What is an operating system?", fill='black', font=font)
    draw.text((50, 290), "Ans: An operating system is system software that", fill='black', font=font_small)
    draw.text((50, 315), "manages computer hardware, software resources, and", fill='black', font=font_small)
    draw.text((50, 340), "provides common services for computer programs.", fill='black', font=font_small)

    draw.text((50, 400), "Q2. Explain process scheduling.", fill='black', font=font)
    draw.text((50, 440), "Ans: Process scheduling is the activity of the", fill='black', font=font_small)
    draw.text((50, 465), "process manager that handles the removal of the", fill='black', font=font_small)
    draw.text((50, 490), "running process from the CPU and the selection", fill='black', font=font_small)
    draw.text((50, 515), "of another process based on a scheduling algorithm.", fill='black', font=font_small)

    # Draw a simple diagram
    draw.text((50, 580), "Q3. Draw a process state diagram:", fill='black', font=font)
    draw.rectangle([100, 620, 200, 660], outline='black', width=2)
    draw.text((115, 630), "Ready", fill='black', font=font_small)
    draw.rectangle([300, 620, 400, 660], outline='black', width=2)
    draw.text((305, 630), "Running", fill='black', font=font_small)
    draw.rectangle([500, 620, 600, 660], outline='black', width=2)
    draw.text((510, 630), "Waiting", fill='black', font=font_small)
    draw.line([200, 640, 300, 640], fill='black', width=2)
    draw.line([400, 640, 500, 640], fill='black', width=2)

    img.save(out_path, "JPEG", quality=90)
    return out_path


# ===================== TEST 5: Pipeline on Test Image =====================
def test_pipeline_with_image(image_path=None):
    print(f"\n{BOLD}Test 4: Pipeline End-to-End{RESET}")

    # Create test image if none provided
    test_dir = os.path.join(SCRIPT_DIR, "_test_output")
    os.makedirs(test_dir, exist_ok=True)

    if not image_path:
        image_path = os.path.join(test_dir, "test_answer_sheet.jpg")
        created = create_test_image(image_path)
        if not created:
            warn("Could not create test image, skipping pipeline test")
            return False
        ok(f"Test image created: {image_path}")
    else:
        if not os.path.exists(image_path):
            fail(f"Input file not found: {image_path}")
            return False
        ok(f"Using provided input: {image_path}")

    try:
        from ocr.enhanced_ocr_pipeline import process_image_file

        result = process_image_file(image_path, test_dir)

        # Validate backward compatibility
        assert "full_text" in result, "Missing 'full_text' field"
        assert "pages" in result, "Missing 'pages' field"
        assert "structured_answers" in result, "Missing 'structured_answers' field"
        ok("Backward-compatible fields present (full_text, pages, structured_answers)")

        # Validate new fields
        assert "student_info" in result, "Missing 'student_info' field"
        assert "content_analysis" in result, "Missing 'content_analysis' field"
        assert "pipeline_mode" in result, "Missing 'pipeline_mode' field"
        ok("Enhanced fields present (student_info, content_analysis, pipeline_mode)")

        # Check pipeline mode
        info(f"Pipeline mode: {result['pipeline_mode']}")
        info(f"Full text: {len(result['full_text'])} chars")
        info(f"Structured answers: {len(result['structured_answers'])}")

        # Print student info
        si = result.get("student_info", {})
        if any(si.values()):
            ok(f"Student info extracted: name='{si.get('name', '')}', "
               f"roll='{si.get('roll_number', '')}', branch='{si.get('branch', '')}'")
        else:
            warn("Student info is empty (may be expected for non-cover-page images)")

        # Print content analysis
        for ca in result.get("content_analysis", []):
            blocks = ca.get("content_blocks", [])
            types = [b.get("type", "?") for b in blocks]
            info(f"Page {ca.get('page_number', '?')}: {len(blocks)} blocks — {', '.join(types)}")

        # Print structured answers
        for sa in result.get("structured_answers", []):
            info(f"Q{sa['question_number']}: {len(sa['answer_text'])} chars")

        # Save result
        result_path = os.path.join(test_dir, "test_result.json")
        with open(result_path, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        ok(f"Full result saved to: {result_path}")

        # Print pretty JSON
        print(f"\n{BOLD}--- Pipeline Output JSON ---{RESET}")
        print(json.dumps(result, indent=2, ensure_ascii=False)[:2000])
        if len(json.dumps(result)) > 2000:
            print(f"... ({len(json.dumps(result))} total chars, truncated)")

        return True

    except Exception as e:
        fail(f"Pipeline test failed: {e}")
        traceback.print_exc()
        return False


# ===================== TEST 6: Gemini Evaluator =====================
def test_evaluator():
    print(f"\n{BOLD}Test 5: Gemini Evaluator{RESET}")

    try:
        from ocr.gemini_evaluator import evaluate_answer

        result = evaluate_answer(
            student_answer="An operating system is software that manages hardware and software resources.",
            model_answer="An operating system (OS) is system software that manages computer hardware, "
                         "software resources, and provides common services for computer programs. "
                         "Examples include Windows, Linux, macOS.",
            max_marks=5,
            content_types=["text"],
            question_number="1"
        )

        ok(f"Evaluator returned: {result['marks_awarded']}/{result['max_marks']}")
        info(f"Reason: {result.get('reason', 'N/A')}")

        # Print result
        print(f"\n  {json.dumps(result, indent=2)}")

        return True

    except Exception as e:
        fail(f"Evaluator test failed: {e}")
        traceback.print_exc()
        return False


# ===================== MAIN =====================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test Enhanced OCR Pipeline")
    parser.add_argument("--input", help="Optional: path to a real PDF or image to test with")
    args = parser.parse_args()

    print(f"\n{BOLD}{'='*60}")
    print(f" EvalAI — Enhanced OCR Pipeline Test Suite")
    print(f"{'='*60}{RESET}\n")

    results = {}

    # Run all tests
    results["imports"] = test_imports()
    results["environment"] = test_environment()
    results["gemini_api"] = test_gemini_connectivity()
    results["pipeline"] = test_pipeline_with_image(args.input)
    results["evaluator"] = test_evaluator()

    # Summary
    print(f"\n{BOLD}{'='*60}")
    print(f" Test Summary")
    print(f"{'='*60}{RESET}\n")

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    failed = total - passed

    for name, result in results.items():
        status = f"{GREEN}PASS{RESET}" if result else f"{RED}FAIL{RESET}"
        print(f"  {status}  {name}")

    print(f"\n  Total: {total} | Passed: {GREEN}{passed}{RESET} | Failed: {RED}{failed}{RESET}")

    if failed > 0:
        print(f"\n  {YELLOW}Some tests failed. Check the output above for details.{RESET}")
        sys.exit(1)
    else:
        print(f"\n  {GREEN}All tests passed! Pipeline is ready.{RESET}")
        sys.exit(0)
