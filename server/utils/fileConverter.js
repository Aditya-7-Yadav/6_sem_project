const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const PYTHON_DIR = path.join(__dirname, '..', '..', 'python');
const PYTHON_PATH = process.env.PYTHON_PATH || 'python';

/**
 * Parse model answer text into structured question objects.
 * 
 * Expected format:
 * Q1 [2 marks]
 * Model answer text for question 1...
 * 
 * Q2 [5 marks]
 * Model answer text for question 2...
 * 
 * Alternative formats supported:
 * 1. [2] Answer text...
 * Q1 (3 marks) Answer text...
 * 1) [2 marks] Answer text...
 */
function parseModelAnswerText(text) {
  const questions = [];

  // Pattern: Q<num> or <num>. or <num>) followed by [<marks>] or (<marks>) or [<marks> marks] etc.
  const questionPattern = /(?:^|\n)\s*(?:Q|q)?(\d+(?:\([a-z]\))?)\s*[.\):]?\s*[\[\(]\s*(\d+)\s*(?:marks?)?\s*[\]\)]/g;

  let match;
  const matches = [];

  while ((match = questionPattern.exec(text)) !== null) {
    matches.push({
      questionNumber: match[1],
      maxMarks: parseInt(match[2]),
      index: match.index,
      fullMatchEnd: match.index + match[0].length
    });
  }

  for (let i = 0; i < matches.length; i++) {
    const current = matches[i];
    const nextIndex = i + 1 < matches.length ? matches[i + 1].index : text.length;
    const answerText = text.substring(current.fullMatchEnd, nextIndex).trim();
    const type = current.maxMarks < 3 ? 'short' : 'long';

    questions.push({
      questionNumber: current.questionNumber,
      modelAnswer: answerText,
      maxMarks: current.maxMarks,
      type: type,
      // Default multimodal fields
      contentTypes: ['text'],
      keywords: [],
      diagramData: null,
      mathExpressions: []
    });
  }

  return questions;
}


/**
 * Process a PDF model answer through the enhanced Python pipeline.
 * Uses Gemini Vision to extract structured content including diagrams, math, keywords.
 * 
 * @param {string} filePath - Path to the PDF file
 * @returns {Promise<Array>} - Array of enriched question objects
 */
function parseModelAnswerPDF(filePath) {
  return new Promise((resolve, reject) => {
    const scriptPath = path.join(PYTHON_DIR, 'ocr', 'enhanced_ocr_pipeline.py');
    const outputDir = path.join(
      path.dirname(filePath),
      `model_processing_${Date.now()}`
    );

    fs.mkdirSync(outputDir, { recursive: true });

    console.log('[FileConverter] Processing PDF model answer with enhanced pipeline');
    console.log('[FileConverter] Script:', scriptPath);
    console.log('[FileConverter] Input:', filePath);
    console.log('[FileConverter] Output dir:', outputDir);

    const proc = spawn(PYTHON_PATH, [
      scriptPath,
      '--input', filePath,
      '--output-dir', outputDir,
      '--mode', 'model-answer',
      '--legacy'
    ], {
      cwd: PYTHON_DIR,
      env: { ...process.env }
    });

    let stdout = '';
    let stderr = '';

    const timeout = setTimeout(() => {
      console.error('[FileConverter] TIMEOUT: Model answer processing exceeded 5 minutes');
      proc.kill('SIGKILL');
    }, 300_000);

    proc.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    proc.stderr.on('data', (data) => {
      stderr += data.toString();
      console.log('[FileConverter Python]', data.toString().trim());
    });

    proc.on('close', (code) => {
      clearTimeout(timeout);

      console.log('[FileConverter] Process exited with code:', code);

      if (!stdout.trim()) {
        // If Python processing failed, fall back to pdf-parse
        console.log('[FileConverter] Python processing produced no output, falling back to pdf-parse');
        parseModelAnswerPDFFallback(filePath)
          .then(resolve)
          .catch(reject);
        return;
      }

      try {
        const result = JSON.parse(stdout.trim());

        if (result.error) {
          console.error('[FileConverter] Python returned error:', result.error);
          // Fall back to pdf-parse
          parseModelAnswerPDFFallback(filePath)
            .then(resolve)
            .catch(reject);
          return;
        }

        // Result is in legacy format (array of question objects)
        if (Array.isArray(result)) {
          console.log(`[FileConverter] Enhanced processing extracted ${result.length} questions`);
          resolve(result);
        } else {
          console.warn('[FileConverter] Unexpected result format, falling back to pdf-parse');
          parseModelAnswerPDFFallback(filePath)
            .then(resolve)
            .catch(reject);
        }

      } catch (e) {
        console.error('[FileConverter] Failed to parse Python output:', e.message);
        parseModelAnswerPDFFallback(filePath)
          .then(resolve)
          .catch(reject);
      }
    });

    proc.on('error', (err) => {
      clearTimeout(timeout);
      console.error('[FileConverter] Failed to start Python process:', err.message);
      // Fall back to pdf-parse
      parseModelAnswerPDFFallback(filePath)
        .then(resolve)
        .catch(reject);
    });
  });
}


/**
 * PDF fallback: extract text using pdf-parse and apply regex parsing.
 * This is the original behavior for PDF model answers.
 */
async function parseModelAnswerPDFFallback(filePath) {
  try {
    const pdfParse = require('pdf-parse');
    const buffer = fs.readFileSync(filePath);
    const data = await pdfParse(buffer);
    console.log(`[FileConverter] pdf-parse fallback extracted ${data.text.length} chars`);
    return parseModelAnswerText(data.text);
  } catch (err) {
    throw new Error(`Failed to parse PDF model answer: ${err.message}`);
  }
}


/**
 * Read and parse a model answer file.
 * - .txt: regex-based parsing (original behavior)
 * - .pdf: enhanced Python pipeline with Gemini Vision, fallback to pdf-parse
 */
async function parseModelAnswerFile(filePath) {
  const ext = path.extname(filePath).toLowerCase();

  if (ext === '.txt') {
    const text = fs.readFileSync(filePath, 'utf-8');
    return parseModelAnswerText(text);
  }

  if (ext === '.pdf') {
    try {
      // Try enhanced processing first (Gemini Vision for diagrams, math, etc.)
      return await parseModelAnswerPDF(filePath);
    } catch (err) {
      console.error('[FileConverter] Enhanced PDF processing failed:', err.message);
      // Fall back to basic pdf-parse
      return await parseModelAnswerPDFFallback(filePath);
    }
  }

  throw new Error(`Unsupported model answer format: ${ext}`);
}


/**
 * Ensure the file is a PDF (convert images to PDF placeholder).
 * For images, we just pass them directly to the OCR service which handles them.
 */
function getFileType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === '.pdf') return 'pdf';
  if (['.jpg', '.jpeg', '.png', '.bmp', '.tiff'].includes(ext)) return 'image';
  return 'unknown';
}


module.exports = { parseModelAnswerText, parseModelAnswerFile, parseModelAnswerPDF, getFileType };

