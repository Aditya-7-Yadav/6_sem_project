from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import sys
import json
import time
import requests
import cv2
import numpy as np
try:
    import fitz  # PyMuPDF
except ImportError as exc:
    raise ImportError("PyMuPDF is required for PDF conversion. Run `pip install PyMuPDF`.") from exc
from PIL import Image
from werkzeug.utils import secure_filename
import tempfile
import shutil
import io

# ===================== ML SHORT ANSWER GRADER SETUP =====================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ML_DIR = os.path.join(BASE_DIR, "ML_Short_Answer")
if ML_DIR not in sys.path:
    sys.path.append(ML_DIR)

from short_answer_grader import ShortAnswerGrader

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend

# Instantiate grader once at startup
grader = ShortAnswerGrader()

# ===================== CONFIG =====================
API_KEY = "K86291774288957"
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
ALLOWED_EXTENSIONS = {'pdf'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

OCR_PAYLOAD = {
    "apikey": API_KEY,
    "language": "eng",
    "ocrengine": 3,
    "scale": True,
    "detectOrientation": True
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ===================== PDF → IMAGES =====================
def pdf_to_images(pdf_path, out_dir, dpi=200):
    os.makedirs(out_dir, exist_ok=True)
    image_paths = []
    try:
        pdf_document = fitz.open(pdf_path)
        for i, page in enumerate(pdf_document, start=1):
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            img = img.convert("L")
            img_path = os.path.join(out_dir, f"page_{i}.jpg")
            img.save(img_path, "JPEG", quality=85)
            image_paths.append(img_path)
        pdf_document.close()
    except Exception as e:
        raise Exception(f"PyMuPDF conversion error: {str(e)}")
    return image_paths

# ===================== HANDWRITING DETECTION =====================
def is_handwritten_page(img_path):
    img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    
    # Edge detection (handwriting has irregular strokes)
    edges = cv2.Canny(img, 50, 150)
    
    # Ratio of edge pixels
    edge_ratio = np.sum(edges > 0) / edges.size
    
    # Printed pages → very low edge density
    # Handwritten pages → higher edge density
    return edge_ratio > 0.015

def find_first_answer_page(image_paths):
    for idx, img in enumerate(image_paths):
        if is_handwritten_page(img):
            return idx + 1  # page number (1-based)
    return 1  # Default to page 1 if no handwritten page detected

# ===================== OCR =====================
def run_ocr(img_path, retries=3):
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
            if not data.get("IsErroredOnProcessing"):
                parsed = data.get("ParsedResults", [])
                if parsed:
                    return parsed[0].get("ParsedText", "").strip()
        except Exception as e:
            print(f"OCR attempt {attempt + 1} failed: {str(e)}")
            time.sleep(5)
    return ""

# ===================== MAIN PIPELINE =====================
def ocr_pdf_pipeline(pdf_path):
    base = os.path.splitext(os.path.basename(pdf_path))[0]
    out_dir = os.path.join(OUTPUT_FOLDER, f"{base}_output")
    os.makedirs(out_dir, exist_ok=True)

    print(f"\n📄 Processing: {pdf_path}")

    # Convert PDF to images
    images = pdf_to_images(pdf_path, out_dir)
    
    # Find first answer page
    start_page = find_first_answer_page(images)
    print(f"✅ Starting from page: {start_page}")

    all_text = []
    
    # Process pages starting from the first answer page
    for idx in range(start_page - 1, len(images)):
        page_num = idx + 1
        img = images[idx]
        print(f"OCR page {page_num}")
        text = run_ocr(img)
        all_text.append(f"\n--- PAGE {page_num} ---\n{text}")
        time.sleep(2)  # Rate limiting

    # Combine all text
    full_text = "\n".join(all_text)
    
    # Save to file
    txt_path = os.path.join(out_dir, f"{base}_answers.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(full_text)

    print("✅ DONE")
    print(f"📄 TXT  → {txt_path}")
    
    return full_text

# ===================== API ENDPOINTS =====================
@app.route('/run', methods=['POST'])
def upload_file():
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file part in the request'}), 400
        
        file = request.files['file']
        
        # Check if file is selected
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Check if file is PDF
        if not allowed_file(file.filename):
            return jsonify({'error': 'Only PDF files are allowed'}), 400
        
        # Save the uploaded file
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        print(f"File saved: {filepath}")
        
        # Process the PDF with OCR
        result_text = ocr_pdf_pipeline(filepath)
        
        # Clean up uploaded file
        try:
            os.remove(filepath)
        except:
            pass
        
        # Return the extracted text
        return jsonify({
            'output': result_text,
            'success': True
        })
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({
            'error': f'Failed to process PDF: {str(e)}',
            'success': False
        }), 500


@app.route('/grade', methods=['POST'])
def grade_answer():
    """Grade a short answer using OCR text and model answer.

    Expected JSON body:
    {
        "student_answer": "..."  # or "ocr_text": "...",
        "model_answer": "...",
        "keywords": { ... }      # optional dict
    }
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'error': 'Invalid or missing JSON body'}), 400

        student_answer = data.get('student_answer') or data.get('ocr_text')
        model_answer = data.get('model_answer')
        keywords = data.get('keywords') or {}

        if not student_answer or not model_answer:
            return jsonify({
                'error': 'student_answer/ocr_text and model_answer are required'
            }), 400

        result = grader.evaluate(student_answer, model_answer, keywords)

        return jsonify({
            'success': True,
            'result': result
        })

    except Exception as e:
        print(f"Grading error: {e}")
        return jsonify({
            'success': False,
            'error': f'Failed to grade answer: {str(e)}'
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'message': 'OCR Backend is running'})

if __name__ == '__main__':
    print("🚀 Starting OCR Backend Server...")
    print("📡 Server will run on http://localhost:3000")
    app.run(host='0.0.0.0', port=3000, debug=True)
