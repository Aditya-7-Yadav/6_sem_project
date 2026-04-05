# OCR Backend Server

Flask backend server for processing PDF files with OCR (Optical Character Recognition).

## Features

- PDF to image conversion
- Handwritten page detection
- OCR using OCR.space API
- CORS enabled for frontend integration
- Multi-page PDF support

## Prerequisites

### Windows

1. **Python 3.8+** installed
2. **Poppler** for PDF processing:
   - Download from: https://github.com/oschwartz10612/poppler-windows/releases/
   - Extract and add `bin` folder to PATH
   - Or use: `choco install poppler` (if you have Chocolatey)

### Alternative: Use conda

```bash
conda install -c conda-forge poppler
```

## Installation

1. **Navigate to backend directory:**
   ```bash
   cd backend
   ```

2. **Create virtual environment (optional but recommended):**
   ```bash
   python -m venv venv
   venv\Scripts\activate  # On Windows
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Running the Server

```bash
python app.py
```

The server will start on `http://localhost:3000`

## API Endpoints

### POST /run
Upload and process a PDF file

**Request:**
- Method: POST
- Content-Type: multipart/form-data
- Body: FormData with key "file" containing PDF

**Response:**
```json
{
  "output": "extracted text from all pages",
  "success": true
}
```

**Error Response:**
```json
{
  "error": "error message",
  "success": false
}
```

### GET /health
Check server status

**Response:**
```json
{
  "status": "healthy",
  "message": "OCR Backend is running"
}
```

## Configuration

Edit the API key in `app.py`:
```python
API_KEY = "K86291774288957"
```

## Troubleshooting

### "Poppler not found" error
- Install Poppler (see Prerequisites)
- Add Poppler's `bin` folder to system PATH
- Restart terminal/IDE

### Import errors
```bash
pip install --upgrade -r requirements.txt
```

### Port already in use
Change port in `app.py`:
```python
app.run(host='0.0.0.0', port=5000, debug=True)
```

## File Structure

```
backend/
├── app.py              # Main Flask application
├── requirements.txt    # Python dependencies
├── uploads/           # Temporary uploaded files
├── outputs/           # OCR output files
└── README.md          # This file
```
