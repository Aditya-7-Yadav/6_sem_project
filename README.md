# OCR Application - Complete Setup Guide

Full-stack application for PDF OCR processing with modern React frontend and Flask backend.

## 🏗️ Project Structure

```
6_sem_project/
├── frontend/           # React + Vite + TailwindCSS
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   └── services/
│   └── package.json
├── backend/            # Flask API server
│   ├── app.py
│   └── requirements.txt
├── Stud_ans_sheet_OCR.ipynb  # Original notebook
└── README.md          # This file
```

## 🚀 Quick Start

### Step 1: Install Poppler (Required for PDF processing)

**Windows:**
1. Download Poppler from: https://github.com/oschwartz10612/poppler-windows/releases/
2. Extract to `C:\Program Files\poppler`
3. Add `C:\Program Files\poppler\Library\bin` to System PATH
4. Restart your terminal

**Or use Chocolatey:**
```bash
choco install poppler
```

**Or use Conda:**
```bash
conda install -c conda-forge poppler
```

### Step 2: Setup Backend

```bash
# Navigate to backend
cd backend

# Create virtual environment (optional)
python -m venv venv
venv\Scripts\activate  # Windows

# Install Python dependencies
pip install -r requirements.txt

# Start the server
python app.py
```

Backend will run on: **http://localhost:3000**

### Step 3: Setup Frontend

Open a **NEW terminal** (keep backend running):

```bash
# Navigate to frontend
cd frontend

# Install dependencies (if not already done)
npm install

# Start development server
npm run dev
```

Frontend will run on: **http://localhost:5173**

## 📖 Usage

1. Open browser to `http://localhost:5173`
2. Login with any credentials (UI only)
3. Upload a PDF file (drag & drop or click)
4. Click "Process Document"
5. Wait for OCR processing
6. View extracted text in the result panel
7. Copy text or upload another file

## 🔧 Configuration

### Backend API Key
Edit [backend/app.py](backend/app.py#L18):
```python
API_KEY = "your_ocr_space_api_key"
```

### Backend Port
Edit [backend/app.py](backend/app.py#L195):
```python
app.run(host='0.0.0.0', port=3000, debug=True)
```

### Frontend API URL
Edit [frontend/.env](frontend/.env):
```
VITE_API_URL=http://localhost:3000
```

## 🛠️ Troubleshooting

### Backend Issues

**"Poppler not found"**
- Install Poppler (see Step 1)
- Verify PATH: `where pdfinfo` (Windows)
- Restart terminal after adding to PATH

**"Port 3000 already in use"**
- Change port in `backend/app.py`
- Update `frontend/.env` with new port

**Import errors**
```bash
pip install --upgrade -r requirements.txt
```

### Frontend Issues

**"Failed to upload file"**
- Ensure backend is running on port 3000
- Check browser console for CORS errors
- Verify `.env` has correct API URL

**Module not found**
```bash
cd frontend
rm -rf node_modules
npm install
```

### CORS Issues
- Backend already has CORS enabled
- If issues persist, check browser console
- Ensure both servers are running

## 🧪 Testing

### Test Backend
```bash
# Check health
curl http://localhost:3000/health

# Or open in browser:
http://localhost:3000/health
```

### Test Frontend
1. Open `http://localhost:5173`
2. Should see login page
3. After login, should see dashboard

## 📦 Production Build

### Frontend
```bash
cd frontend
npm run build
# Output in frontend/dist/
```

### Backend
Use production WSGI server:
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:3000 app:app
```

## 🔑 Features

### Frontend
- Modern, responsive UI
- Drag & drop PDF upload
- Real-time progress indicator
- Text viewer with copy-to-clipboard
- Error handling & loading states

### Backend
- PDF to image conversion
- Handwritten page detection
- Multi-page OCR processing
- Rate limiting for API calls
- File cleanup after processing

## 📝 API Documentation

### POST /run
Upload and process PDF

**Request:**
```bash
curl -X POST http://localhost:3000/run \
  -F "file=@document.pdf"
```

**Response:**
```json
{
  "output": "Extracted text from all pages...",
  "success": true
}
```

### GET /health
Server health check

**Response:**
```json
{
  "status": "healthy",
  "message": "OCR Backend is running"
}
```

## 🐛 Common Errors

| Error | Solution |
|-------|----------|
| CORS error | Ensure backend is running with flask-cors |
| Connection refused | Start backend server first |
| PDF conversion failed | Install Poppler correctly |
| OCR timeout | Check internet connection, OCR.space API might be slow |
| File upload failed | Check file is valid PDF, max 10MB |

## 📚 Tech Stack

### Frontend
- React 18
- Vite
- TailwindCSS
- React Router
- Axios

### Backend
- Flask
- pdf2image
- OpenCV
- Pillow
- OCR.space API

## 🔐 Security Notes

- Current setup is for development only
- No real authentication implemented (UI only)
- API key is hardcoded (move to environment variables for production)
- Add rate limiting for production
- Implement proper file validation
- Add user authentication

## 📄 License

MIT

## 🤝 Support

For issues:
1. Check this README troubleshooting section
2. Verify both servers are running
3. Check browser console for errors
4. Check terminal output for backend errors
