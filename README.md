# EvalAI — AI Answer Sheet Evaluation System

MERN stack application with **Hybrid OCR + Gemini AI** pipeline for automated answer sheet grading.

## ✨ Features

- **Hybrid OCR + AI Pipeline** — OCRSpace for text + Google Gemini for visual content
- **First Page Intelligence** — Automatically extracts student name, roll number, branch from cover page
- **Content Classification** — Detects text, diagrams, graphs, numericals, and theorems
- **AI-Based Evaluation** — Gemini evaluates diagrams & graphs; ML models grade text answers
- **Graceful Fallback** — Falls back to OCR-only if Gemini is unavailable

## 🚀 Quick Start

### Prerequisites
- **Node.js** 18+ (`node --version`)
- **Python** 3.10+ (`python3 --version`)
- **MongoDB** 6.0+ running locally on port 27017
- **poppler-utils** (`sudo apt install poppler-utils`)

### 1. Clone & Setup Environment

```bash
git clone <repo-url>
cd 6_sem_project

# Create .env files from templates
cp server/.env.example server/.env
cp python/.env.example python/.env
# Edit both files with your actual API keys
```

### 2. Install Dependencies

```bash
# Python
cd python
pip install --break-system-packages -r requirements.txt
cd ..

# Server
cd server && npm install && cd ..

# Client
cd client && npm install && cd ..
```

> **Note:** First run downloads ML models (~500MB for sentence-transformers).
> Install `poppler-utils` for PDF processing:
> - Linux: `sudo apt install poppler-utils`
> - Mac: `brew install poppler`
> - Windows: [poppler releases](https://github.com/oschwartz10612/poppler-windows/releases)

### 3. Start MongoDB

```bash
sudo systemctl start mongod
```

### 4. Start Backend (Terminal 1)

```bash
cd server
npm start
```
Server runs on http://localhost:5000

### 5. Start Frontend (Terminal 2)

```bash
cd client
npm run dev
```
Client runs on http://localhost:5173

### 6. Login

- **Username:** `admin`
- **Password:** `admin123`

(Auto-created on first server startup)

## 📝 Model Answer File Format

Upload a `.txt` file:
```
Q1 [2]
The throw keyword is used to explicitly throw an exception in Java.

Q2 [5]
Object-oriented programming is a paradigm based on objects...

Q3 [1]
JVM
```

- `Q<number> [<marks>]` — question number and maximum marks
- Questions with < 3 marks → evaluated as **short answers**
- Questions with ≥ 3 marks → evaluated as **long answers**

## 🔑 Environment Variables

### server/.env
```
PORT=5000
MONGODB_URI=mongodb://localhost:27017/answer_evaluator
JWT_SECRET=your_secret_here
PYTHON_PATH=python3
OCR_API_KEY=your_ocr_space_key
GEMINI_API_KEY=your_gemini_key
CLIENT_URL=http://localhost:5173
```

### python/.env
```
GEMINI_API_KEY=your_gemini_key
OCR_API_KEY=your_ocr_space_key
```

## 🏗️ Architecture

```
Upload PDF → Split Pages → First Page (Gemini: student info)
                         → All Pages: OCRSpace text + Gemini classification
                         → Hybrid Merge → Extract Q&A
                         → Match with Model Answers → Grade → Display Results
```

## 📁 Project Structure

```
├── client/          # React frontend (Vite)
├── server/          # Express.js API + MongoDB
│   └── services/
│       └── pythonBridge.js    # Spawns Python processes
├── python/          # AI & OCR engine
│   ├── ocr_service.py         # Original OCR pipeline
│   ├── grader_service.py      # ML-based grader
│   ├── ocr/                   # Enhanced pipeline
│   │   ├── enhanced_ocr_pipeline.py
│   │   ├── gemini_client.py
│   │   ├── gemini_first_page_extractor.py
│   │   ├── content_classifier.py
│   │   ├── hybrid_extractor.py
│   │   └── gemini_evaluator.py
│   └── test_enhanced_pipeline.py
└── uploads/         # Uploaded files (gitignored)
```

## 🧪 Testing

```bash
cd python
python3 test_enhanced_pipeline.py
```

## Tech Stack
- **Frontend**: React + Vite + Framer Motion
- **Backend**: Node.js + Express
- **Database**: MongoDB + Mongoose
- **AI/ML**: Python (sentence-transformers, Google Gemini)
- **OCR**: OCRSpace API + Gemini Vision
