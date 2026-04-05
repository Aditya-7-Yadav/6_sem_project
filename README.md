# EvalAI — AI Answer Sheet Evaluation System

MERN stack application with Python AI services for automated answer sheet grading.

## Quick Start

### Prerequisites
- Node.js 18+
- MongoDB running locally (port 27017)
- Python 3.9+ with pip

### 1. Install Python dependencies
```bash
cd python
pip install -r requirements.txt
```
> Note: First run will download ML models (~500MB). Also install `poppler` for PDF processing:
> - Windows: Download from [poppler releases](https://github.com/oschwartz10612/poppler-windows/releases) and add to PATH
> - Mac: `brew install poppler`
> - Linux: `apt-get install poppler-utils`

### 2. Install & start backend
```bash
cd server
npm install
npm run dev
```
Server runs on http://localhost:5000

### 3. Install & start frontend
```bash
cd client
npm install
npm run dev
```
Client runs on http://localhost:5173

### 4. Login
- Username: `admin`
- Password: `admin123`

## Model Answer File Format

Upload a `.txt` file with this format:
```
Q1 [2]
The throw keyword is used to explicitly throw an exception in Java.

Q2 [5]
Object-oriented programming is a paradigm based on objects...

Q3 [1]
JVM
```

- `Q<number> [<marks>]` — question number and marks
- Questions with < 3 marks → evaluated as **short answers**
- Questions with ≥ 3 marks → evaluated as **long answers**

## Architecture

```
Upload → Convert → OCR → Parse → Classify → Evaluate → Aggregate → Store → Display
```

## Tech Stack
- **Frontend**: React + Vite + Framer Motion
- **Backend**: Node.js + Express
- **Database**: MongoDB + Mongoose
- **AI/ML**: Python (sentence-transformers, roberta-large-mnli)
- **OCR**: ocr.space API
