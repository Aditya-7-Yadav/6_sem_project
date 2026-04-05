# 🧠 Automated Answer Evaluation System

An AI-powered web application that evaluates handwritten or typed answer sheets by converting them into text and comparing them with model answers to generate scores and feedback.

---

## 🚀 Features

* 📄 Upload answer sheet (PDF/Image)
* 🔍 OCR-based text extraction
* 📝 Model answer input
* 🤖 Automated evaluation using ML/NLP
* 📊 Score generation with feedback
* 🌐 Full-stack web interface

---

## 🏗️ Architecture

```
Frontend (React)
        ↓
Backend (Node.js / Express)
        ↓
OCR Service (Python)
        ↓
Text Extraction
        ↓
ML Evaluation Service (Python)
        ↓
Score + Feedback
        ↓
Frontend Display
```

---

## 🛠️ Tech Stack

### Frontend

* React (Vite)
* Tailwind CSS

### Backend

* Node.js
* Express.js

### Python Services

* Flask / FastAPI
* OpenCV
* PyMuPDF
* Tesseract OCR

### Database

* MongoDB Atlas (optional)

---

## ⚙️ Setup Instructions

### 1. Clone Repository

```bash
git clone https://github.com/your-username/auto-answer-checker.git
cd auto-answer-checker
```

---

### 2. Backend Setup

```bash
cd backend
npm install
npm run dev
```

---

### 3. Python OCR Service Setup

```bash
cd ..
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
python backend/app.py
```

---

### 4. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

---

## 🔗 API Endpoints

### OCR Service

```
POST /extract-text
Input: PDF/Image
Output: Extracted text
```

### Evaluation Service

```
POST /evaluate
Input:
{
  "student_text": "...",
  "model_answer": "..."
}

Output:
{
  "total_score": 85,
  "per_question_scores": [],
  "feedback": []
}
```

---

## 📸 Workflow

1. User uploads answer sheet
2. OCR extracts text
3. Model answer is provided
4. ML model compares answers
5. Score + feedback generated

---

## ⚠️ Challenges

* OCR accuracy for handwritten text
* Text segmentation into questions
* Semantic similarity evaluation
* Handling large PDFs

---

## 💡 Future Improvements

* Better NLP models (BERT / LLM-based scoring)
* Highlight incorrect answers
* Multi-subject support
* Authentication system
* Deployment on cloud

---

## 👥 Team

* Backend & Integration: *You*
* OCR Module: Team Member
* ML Model: Team Members

---

## 📌 Status

🚧 In Development

---

## ⭐ Contribution

Pull requests are welcome. For major changes, please open an issue first.

---

## 📄 License

This project is for educational purposes.
