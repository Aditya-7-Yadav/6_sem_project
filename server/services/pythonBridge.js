const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const PYTHON_DIR = path.join(__dirname, '..', '..', 'python');
const PYTHON_PATH = process.env.PYTHON_PATH || 'python';

// Timeout for OCR process (5 minutes — hybrid pipeline with Gemini takes longer)
const OCR_TIMEOUT_MS = 300_000;
// Timeout for grader process
// 5 minutes — models take time to load on first request
const GRADER_TIMEOUT_MS = 300_000;

/**
 * Normalize a file path for cross-platform compatibility.
 * Resolves to absolute path and ensures it exists.
 */
function normalizePath(filePath) {
  const resolved = path.resolve(filePath);
  return resolved;
}

/**
 * Run the OCR service on a file.
 * @param {string} inputPath - Path to the PDF or image file
 * @param {string} outputDir - Directory to write output files
 * @returns {Promise<object>} - OCR result JSON
 */
function runOCR(inputPath, outputDir) {
  return new Promise((resolve, reject) => {
    // Use enhanced pipeline (falls back to OCR-only if Gemini unavailable)
    const scriptPath = path.join(PYTHON_DIR, 'ocr', 'enhanced_ocr_pipeline.py');
    const normalizedInput = normalizePath(inputPath);
    const normalizedOutput = normalizePath(outputDir);

    // Pre-flight checks
    console.log('[OCR Bridge] ================================');
    console.log('[OCR Bridge] Starting OCR process');
    console.log('[OCR Bridge] Script:', scriptPath);
    console.log('[OCR Bridge] Input file:', normalizedInput);
    console.log('[OCR Bridge] Output dir:', normalizedOutput);
    console.log('[OCR Bridge] Python path:', PYTHON_PATH);
    console.log('[OCR Bridge] File exists:', fs.existsSync(normalizedInput));

    if (!fs.existsSync(normalizedInput)) {
      reject(new Error(`Input file does not exist: ${normalizedInput}`));
      return;
    }

    const fileStats = fs.statSync(normalizedInput);
    console.log('[OCR Bridge] File size:', fileStats.size, 'bytes');

    // Ensure output dir exists
    fs.mkdirSync(normalizedOutput, { recursive: true });

    const proc = spawn(PYTHON_PATH, [
      scriptPath,
      '--input', normalizedInput,
      '--output-dir', normalizedOutput
    ], {
      cwd: PYTHON_DIR,
      env: { ...process.env }
    });

    let stdout = '';
    let stderr = '';
    let timedOut = false;

    // Set timeout
    const timeout = setTimeout(() => {
      timedOut = true;
      console.error('[OCR Bridge] TIMEOUT: OCR process exceeded', OCR_TIMEOUT_MS / 1000, 'seconds');
      proc.kill('SIGKILL');
    }, OCR_TIMEOUT_MS);

    proc.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    proc.stderr.on('data', (data) => {
      const msg = data.toString().trim();
      stderr += msg + '\n';
      // Log progress messages from Python
      console.log('[OCR Python]', msg);
    });

    proc.on('close', (code) => {
      clearTimeout(timeout);

      if (timedOut) {
        reject(new Error('OCR process timed out after ' + (OCR_TIMEOUT_MS / 1000) + ' seconds'));
        return;
      }

      console.log('[OCR Bridge] Process exited with code:', code);
      console.log('[OCR Bridge] stdout length:', stdout.length, 'chars');

      if (code !== 0 && !stdout.trim()) {
        console.error('[OCR Bridge] Process failed. stderr:', stderr);
        reject(new Error(`OCR process exited with code ${code}: ${stderr}`));
        return;
      }

      if (!stdout.trim()) {
        console.error('[OCR Bridge] No stdout output from OCR process');
        reject(new Error('OCR process produced no output'));
        return;
      }

      try {
        const result = JSON.parse(stdout.trim());

        if (result.error) {
          console.error('[OCR Bridge] OCR returned error:', result.error);
          reject(new Error(result.error));
          return;
        }

        // Log summary
        console.log('[OCR Bridge] OCR completed successfully');
        console.log('[OCR Bridge] Full text length:', (result.full_text || '').length);
        console.log('[OCR Bridge] Structured answers:', (result.structured_answers || []).length);
        if (result.warning) {
          console.warn('[OCR Bridge] Warning:', result.warning);
        }

        if (!result.full_text && (!result.structured_answers || result.structured_answers.length === 0)) {
          console.warn('[OCR Bridge] WARNING: OCR returned empty text and no structured answers');
        }

        resolve(result);
      } catch (e) {
        console.error('[OCR Bridge] Failed to parse JSON output');
        console.error('[OCR Bridge] Raw stdout (first 500):', stdout.substring(0, 500));
        reject(new Error(`Failed to parse OCR output: ${stdout.substring(0, 500)}`));
      }
    });

    proc.on('error', (err) => {
      clearTimeout(timeout);
      console.error('[OCR Bridge] Failed to start process:', err.message);
      reject(new Error(`Failed to start OCR process: ${err.message}`));
    });
  });
}

/**
 * Run the grader service on a batch of questions.
 * @param {Array} questions - Array of question objects to grade
 * @returns {Promise<Array>} - Array of grading results
 */
function runGrader(questions) {
  return new Promise((resolve, reject) => {
    const scriptPath = path.join(PYTHON_DIR, 'grader_service.py');

    console.log('[Grader Bridge] Starting grader process');
    console.log('[Grader Bridge] Questions to grade:', questions.length);

    const proc = spawn(PYTHON_PATH, [scriptPath], {
      cwd: PYTHON_DIR,
      env: { ...process.env }
    });

    let stdout = '';
    let stderr = '';
    let timedOut = false;

    const timeout = setTimeout(() => {
      timedOut = true;
      console.error(`[Grader Bridge] TIMEOUT: Grader process exceeded ${GRADER_TIMEOUT_MS / 1000}s. Models may still be loading.`);
      proc.kill('SIGKILL');
    }, GRADER_TIMEOUT_MS);

    proc.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    proc.stderr.on('data', (data) => {
      stderr += data.toString();
      console.log('[Grader Python]', data.toString().trim());
    });

    // Send questions as JSON via stdin
    const input = JSON.stringify(questions);
    proc.stdin.write(input);
    proc.stdin.end();

    proc.on('close', (code) => {
      clearTimeout(timeout);

      if (timedOut) {
        reject(new Error(`Grader process timed out after ${GRADER_TIMEOUT_MS / 1000} seconds. The ML models may need more time to load on first run. Please try again.`));
        return;
      }

      console.log('[Grader Bridge] Process exited with code:', code);

      if (code !== 0 && !stdout.trim()) {
        reject(new Error(`Grader process exited with code ${code}: ${stderr}`));
        return;
      }
      try {
        const result = JSON.parse(stdout.trim());
        if (result.error) {
          reject(new Error(result.error));
        } else {
          console.log('[Grader Bridge] Grading completed:', Array.isArray(result) ? result.length + ' results' : 'single result');
          resolve(result);
        }
      } catch (e) {
        reject(new Error(`Failed to parse grader output: ${stdout.substring(0, 500)}`));
      }
    });

    proc.on('error', (err) => {
      clearTimeout(timeout);
      reject(new Error(`Failed to start grader process: ${err.message}`));
    });
  });
}

module.exports = { runOCR, runGrader };
