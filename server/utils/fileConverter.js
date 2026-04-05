const fs = require('fs');
const path = require('path');

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
      type: type
    });
  }

  return questions;
}


/**
 * Read and parse a model answer file (TXT or extract text from simple PDF).
 */
async function parseModelAnswerFile(filePath) {
  const ext = path.extname(filePath).toLowerCase();

  if (ext === '.txt') {
    const text = fs.readFileSync(filePath, 'utf-8');
    return parseModelAnswerText(text);
  }

  if (ext === '.pdf') {
    try {
      const pdfParse = require('pdf-parse');
      const buffer = fs.readFileSync(filePath);
      const data = await pdfParse(buffer);
      return parseModelAnswerText(data.text);
    } catch (err) {
      throw new Error(`Failed to parse PDF model answer: ${err.message}`);
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


module.exports = { parseModelAnswerText, parseModelAnswerFile, getFileType };
