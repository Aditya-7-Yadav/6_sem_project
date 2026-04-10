#!/usr/bin/env python3
"""
Test Script for Enhanced OCR Pipeline
--------------------------------------
Verifies that all modules import correctly, Gemini API connectivity works,
and the pipeline produces valid output.

Now includes tests for:
  - Model Answer Processor
  - Segmentation Engine
  - Alignment Engine
  - Math Evaluator
  - Diagram Evaluator
  - Full integration test

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
        ("ocr.model_answer_processor", "Model answer processor"),
        ("ocr.segmentation_engine", "Segmentation engine"),
        ("ocr.alignment_engine", "Alignment engine"),
        ("ocr.diagram_evaluator", "Diagram evaluator"),
        ("ocr.math_evaluator", "Math evaluator"),
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

    # Check SymPy
    try:
        import sympy
        ok(f"SymPy available (v{sympy.__version__})")
    except ImportError:
        warn("SymPy not installed — math evaluator will use Gemini fallback")

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


# ===================== TEST 7: Model Answer Processor =====================
def test_model_answer_processor():
    print(f"\n{BOLD}Test 6: Model Answer Processor{RESET}")

    try:
        from ocr.model_answer_processor import (
            parse_model_answer_text_regex, extract_keywords, to_legacy_format
        )

        # Test regex parsing with a synthetic model answer
        model_text = """
Q1(a) [3 marks]
An operating system is system software that manages computer hardware,
software resources, and provides common services for computer programs.
Key concepts: resource management, process scheduling, memory management.

Q1(b) [5 marks]
Process scheduling is the activity of the process manager that handles
the removal of the running process from the CPU and the selection of
another process based on a particular strategy. Types include FCFS,
SJF, Round Robin, Priority scheduling.

Q2 [4 marks]
Calculate the throughput of the system using: throughput = processes / time.
Given 10 processes in 5 seconds, throughput = 10/5 = 2 processes/second.
"""

        questions = parse_model_answer_text_regex(model_text)

        assert len(questions) >= 3, f"Expected ≥3 questions, got {len(questions)}"
        ok(f"Regex parser extracted {len(questions)} questions")

        # Check question content
        for q_num, q_data in questions.items():
            info(f"  Q{q_num}: {q_data['marks']} marks, type={q_data['type']}, "
                 f"content={q_data['content_types']}, keywords={len(q_data['keywords'])}")

        # Test keyword extraction
        keywords = extract_keywords(
            "Operating system manages hardware resources processes memory scheduling"
        )
        assert len(keywords) > 0, "Should extract at least some keywords"
        ok(f"Keyword extraction: {keywords[:5]}")

        # Test legacy format conversion
        model_result = {
            "questions": questions,
            "total_marks": sum(q["marks"] for q in questions.values()),
            "question_structure": list(questions.keys())
        }
        legacy = to_legacy_format(model_result)
        assert len(legacy) == len(questions), "Legacy format should have same number of questions"
        assert "questionNumber" in legacy[0], "Legacy format should have 'questionNumber' field"
        assert "contentTypes" in legacy[0], "Legacy format should have 'contentTypes' field"
        assert "keywords" in legacy[0], "Legacy format should have 'keywords' field"
        ok("Legacy format conversion works correctly")

        return True

    except Exception as e:
        fail(f"Model answer processor test failed: {e}")
        traceback.print_exc()
        return False


# ===================== TEST 8: Segmentation Engine =====================
def test_segmentation_engine():
    print(f"\n{BOLD}Test 7: Segmentation Engine{RESET}")

    try:
        from ocr.segmentation_engine import segment_student_answers, normalize_question_number

        # Test question number normalization
        assert normalize_question_number("Q1(a)") == "1(a)"
        assert normalize_question_number("Ans 2") == "2"
        assert normalize_question_number("  q 3 (b)  ") == "3(b)"
        ok("Question number normalization works")

        # Test segmentation with mock data
        student_text = """
Q1. An operating system manages hardware and software resources.
It provides an interface between users and computer hardware.

Q2. Process scheduling handles CPU allocation among processes.
Common algorithms include FCFS, SJF, and Round Robin.
Priority scheduling assigns priorities to each process.

Ans 3. Memory management involves allocation and deallocation
of memory blocks to programs. It uses paging and segmentation.
"""

        model_structure = {
            "questions": {
                "1": {"text": "An OS is system software that manages hardware...", "marks": 3, "type": "short"},
                "2": {"text": "Process scheduling manages CPU allocation...", "marks": 5, "type": "long"},
                "3": {"text": "Memory management handles allocation...", "marks": 4, "type": "long"},
            },
            "question_structure": ["1", "2", "3"]
        }

        result = segment_student_answers(student_text, model_structure)

        assert "segments" in result, "Missing 'segments' key"
        assert "strategy_used" in result, "Missing 'strategy_used' key"
        ok(f"Segmentation strategy: {result['strategy_used']}")

        matched = sum(1 for s in result["segments"].values() if s["text"])
        total = len(result["segments"])
        ok(f"Matched {matched}/{total} questions")

        for q_num, seg in result["segments"].items():
            text_preview = seg["text"][:50] + "..." if len(seg["text"]) > 50 else seg["text"]
            info(f"  Q{q_num}: confidence={seg['confidence']:.2f}, "
                 f"source={seg['source']}, text='{text_preview}'")

        assert matched >= 2, f"Should match at least 2/3 questions, got {matched}"
        return True

    except Exception as e:
        fail(f"Segmentation engine test failed: {e}")
        traceback.print_exc()
        return False


# ===================== TEST 9: Alignment Engine =====================
def test_alignment_engine():
    print(f"\n{BOLD}Test 8: Alignment Engine{RESET}")

    try:
        from ocr.alignment_engine import align_answers, to_grading_input

        student_segments = {
            "segments": {
                "1": {"text": "An OS manages hardware", "confidence": 0.9, "source": "regex"},
                "2": {"text": "Scheduling allocates CPU time", "confidence": 0.8, "source": "regex"},
                "3": {"text": "", "confidence": 0.0, "source": "regex"},
            },
            "strategy_used": "regex"
        }

        model_structure = {
            "questions": {
                "1": {
                    "text": "An operating system manages hardware",
                    "keywords": ["operating system", "hardware", "software"],
                    "content_types": ["text"],
                    "marks": 3,
                    "type": "short"
                },
                "2": {
                    "text": "Process scheduling handles CPU allocation",
                    "keywords": ["scheduling", "CPU", "process"],
                    "content_types": ["text"],
                    "marks": 5,
                    "type": "long"
                },
                "3": {
                    "text": "Memory management handles allocation",
                    "keywords": ["memory", "allocation", "paging"],
                    "content_types": ["text", "diagram"],
                    "diagram": {"description": "Memory layout diagram", "elements": ["heap", "stack"]},
                    "marks": 4,
                    "type": "long"
                },
            },
            "question_structure": ["1", "2", "3"]
        }

        result = align_answers(student_segments, model_structure)

        assert "aligned_pairs" in result, "Missing 'aligned_pairs'"
        assert "summary" in result, "Missing 'summary'"
        ok(f"Alignment produced {len(result['aligned_pairs'])} pairs")

        summary = result["summary"]
        info(f"  Matched: {summary['matched_questions']}/{summary['total_questions']}")
        info(f"  High confidence: {summary['high_confidence']}")
        info(f"  Low confidence: {summary['low_confidence']}")
        info(f"  Unmatched: {summary['unmatched']}")
        info(f"  Overall confidence: {summary['overall_confidence']}")

        # Test grading input conversion
        grading_input = to_grading_input(result)
        assert len(grading_input) == 3, "Should have 3 grading inputs"
        assert "content_types" in grading_input[0], "Should have content_types"
        assert "diagram_data" in grading_input[2], "Q3 should have diagram_data"
        ok("Grading input conversion works correctly")

        return True

    except Exception as e:
        fail(f"Alignment engine test failed: {e}")
        traceback.print_exc()
        return False


# ===================== TEST 10: Math Evaluator =====================
def test_math_evaluator():
    print(f"\n{BOLD}Test 9: Math Evaluator{RESET}")

    try:
        from ocr.math_evaluator import evaluate_math, SYMPY_AVAILABLE

        info(f"SymPy available: {SYMPY_AVAILABLE}")

        # Test with a numerical comparison
        result = evaluate_math(
            student_answer="throughput = 10/5 = 2 processes/second",
            model_answer="throughput = processes/time = 10/5 = 2 processes/second",
            model_expressions=["10/5 = 2"],
            max_marks=4,
            question_number="test"
        )

        ok(f"Math evaluation: {result['marks_awarded']}/{result['max_marks']} "
           f"(score={result['math_score']}, type={result['evaluation_type']})")
        info(f"  Reason: {result.get('reason', 'N/A')}")

        assert result["marks_awarded"] >= 0, "Marks should be non-negative"
        assert result["max_marks"] == 4, "Max marks should be 4"
        assert "math_score" in result, "Should have math_score"

        # Test with wrong answer
        wrong_result = evaluate_math(
            student_answer="throughput = 10/5 = 3",
            model_answer="throughput = 10/5 = 2",
            max_marks=4,
            question_number="test_wrong"
        )
        info(f"  Wrong answer result: {wrong_result['marks_awarded']}/{wrong_result['max_marks']}")

        # Test with empty answer
        empty_result = evaluate_math(
            student_answer="",
            model_answer="x = 5",
            max_marks=4,
            question_number="test_empty"
        )
        assert empty_result["marks_awarded"] == 0, "Empty answer should get 0 marks"
        ok("Empty answer correctly gets 0 marks")

        return True

    except Exception as e:
        fail(f"Math evaluator test failed: {e}")
        traceback.print_exc()
        return False


# ===================== TEST 11: Diagram Evaluator =====================
def test_diagram_evaluator():
    print(f"\n{BOLD}Test 10: Diagram Evaluator{RESET}")

    try:
        from ocr.diagram_evaluator import evaluate_diagram

        # Test with no image (should return fallback result)
        result = evaluate_diagram(
            image_path="/nonexistent/path.jpg",
            model_diagram_data={
                "description": "Process state diagram",
                "elements": ["Ready", "Running", "Waiting"],
                "connections": [["Ready", "Running"], ["Running", "Waiting"]]
            },
            model_text="Process state transition diagram",
            max_marks=5,
            question_number="test"
        )

        assert "marks_awarded" in result, "Should have marks_awarded"
        assert "diagram_score" in result, "Should have diagram_score"
        ok(f"No-image fallback: {result['marks_awarded']}/{result['max_marks']} "
           f"(type={result['evaluation_type']})")

        # Test with actual test image if available
        test_dir = os.path.join(SCRIPT_DIR, "_test_output")
        test_img = os.path.join(test_dir, "test_answer_sheet.jpg")
        if os.path.exists(test_img):
            from ocr.gemini_client import GEMINI_AVAILABLE
            if GEMINI_AVAILABLE:
                real_result = evaluate_diagram(
                    image_path=test_img,
                    model_diagram_data={
                        "description": "Process state diagram with Ready, Running, Waiting states",
                        "elements": ["Ready", "Running", "Waiting"],
                        "connections": [["Ready", "Running"], ["Running", "Waiting"]]
                    },
                    max_marks=5,
                    question_number="test_real"
                )
                ok(f"Real image eval: {real_result['marks_awarded']}/{real_result['max_marks']} "
                   f"(type={real_result['evaluation_type']})")
            else:
                warn("Gemini not available, skipping real image diagram test")
        else:
            warn("Test image not available, skipping real diagram evaluation")

        return True

    except Exception as e:
        fail(f"Diagram evaluator test failed: {e}")
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
    results["model_answer_processor"] = test_model_answer_processor()
    results["segmentation_engine"] = test_segmentation_engine()
    results["alignment_engine"] = test_alignment_engine()
    results["math_evaluator"] = test_math_evaluator()
    results["diagram_evaluator"] = test_diagram_evaluator()

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

