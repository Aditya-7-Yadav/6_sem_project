const express = require('express');
const path = require('path');
const fs = require('fs');
const authMiddleware = require('../middleware/auth');
const Submission = require('../models/Submission');
const Result = require('../models/Result');
const EvalSet = require('../models/EvalSet');
const { runOCR, runGrader, runSegmentation } = require('../services/pythonBridge');

const router = express.Router();

/**
 * Normalize a question number string for matching.
 * Strips prefixes like Q, q, Ans, Answer, A, and non-alphanumeric chars.
 * Returns just the core number, e.g. "1", "2", "3(a)"
 */
function normalizeQuestionNumber(qnum) {
  if (!qnum) return '';
  let s = String(qnum).trim();
  // Remove common prefixes
  s = s.replace(/^(?:q(?:uestion)?|ans(?:wer)?|a)\s*/i, '');
  // Remove leading punctuation
  s = s.replace(/^[.):;\s]+/, '');
  // Remove trailing punctuation
  s = s.replace(/[.):;\s]+$/, '');
  // Lowercase for comparison
  return s.toLowerCase().trim();
}

/**
 * Match student answers to model answers by question number.
 * Handles out-of-sequence answers, sub-questions (e.g., Q1(a), Q1(b)),
 * and the common case where OCR treats the entire paper as a single Q1.
 * Returns an array of matched pairs ready for grading.
 */
function matchAnswers(studentAnswers, modelAnswers) {
  const matched = [];

  console.log('[Match] Student answers:', studentAnswers.map(sa => `Q${sa.questionNumber}`).join(', '));
  console.log('[Match] Model answers:', modelAnswers.map(ma => `Q${ma.questionNumber}`).join(', '));

  // Build a lookup of student answers by normalized question number
  const studentLookup = {};
  for (const sa of studentAnswers) {
    const key = normalizeQuestionNumber(sa.questionNumber);
    studentLookup[key] = sa;
  }

  // Track how many model questions had no direct match
  let unmatchedCount = 0;
  const unmatchedIndices = [];

  for (let i = 0; i < modelAnswers.length; i++) {
    const model = modelAnswers[i];
    const modelQNum = normalizeQuestionNumber(model.questionNumber);

    // Try exact match first
    let studentMatch = studentLookup[modelQNum];

    // If no exact match, try matching by base number
    // e.g., model has "1(a)" → try matching student's "1"
    if (!studentMatch) {
      const baseNum = modelQNum.replace(/[\(\)a-z]/g, '').trim();
      if (baseNum && studentLookup[baseNum]) {
        studentMatch = studentLookup[baseNum];
      }
    }

    if (studentMatch) {
      console.log(`[Match] Q${modelQNum}: matched (${studentMatch.answerText.length} chars)`);
    } else {
      console.log(`[Match] Q${modelQNum}: no student answer found`);
      unmatchedCount++;
      unmatchedIndices.push(i);
    }

    matched.push({
      questionNumber: model.questionNumber,
      studentAnswer: studentMatch ? studentMatch.answerText : '',
      modelAnswer: model.modelAnswer,
      maxMarks: model.maxMarks,
      type: model.type
    });
  }

  // SMART FALLBACK: If most model questions have no match, but we have full text
  // from a single Q1 blob (common with handwritten papers), distribute
  // the full text proportionally among all model questions.
  const totalModelQs = modelAnswers.length;
  if (unmatchedCount > 0 && studentAnswers.length === 1 && totalModelQs > 1) {
    const fullText = studentAnswers[0].answerText || '';

    if (fullText.length > 100) {
      console.log(`[Match] SMART FALLBACK: OCR returned single blob (${fullText.length} chars) for ${totalModelQs} model questions`);
      console.log(`[Match] Distributing full text to all ${totalModelQs} questions for grading`);

      // Give the full text to every unmatched question —
      // the grader will compare against each model answer and score accordingly.
      // This is better than 0/0 since the grader uses semantic similarity.
      for (const idx of unmatchedIndices) {
        matched[idx].studentAnswer = fullText;
      }
    }
  }

  return matched;
}


/**
 * Generate feedback based on grading details
 */
function generateFeedback(result, type) {
  const marks = result.marks_awarded || 0;
  const max = result.max_marks || 1;
  const pct = max > 0 ? (marks / max) * 100 : 0;

  if (pct >= 90) return 'Excellent answer! Well covered all key points.';
  if (pct >= 70) return 'Good answer with most key concepts covered.';
  if (pct >= 50) return 'Partial answer. Some important points are missing.';
  if (pct >= 25) return 'Needs improvement. Several key concepts are missing.';
  if (marks > 0) return 'Minimal coverage. Review the model answer for key points.';
  return 'No relevant content found. Please refer to the model answer.';
}

// POST /api/process/:submissionId
router.post('/:submissionId', authMiddleware, async (req, res) => {
  const { submissionId } = req.params;

  try {
    // Find submission
    const submission = await Submission.findOne({
      _id: submissionId,
      userId: req.user._id
    });

    if (!submission) {
      return res.status(404).json({ error: 'Submission not found' });
    }

    if (submission.status === 'processing') {
      return res.status(409).json({ error: 'Submission is already being processed' });
    }

    // Update status to processing
    submission.status = 'processing';
    await submission.save();

    // Send immediate response
    res.json({
      message: 'Processing started',
      submissionId: submission._id,
      status: 'processing'
    });

    // Continue processing in background
    processSubmission(submission).catch(err => {
      console.error('Background processing error:', err);
    });

  } catch (error) {
    console.error('Process initiation error:', error);
    res.status(500).json({ error: 'Failed to start processing: ' + error.message });
  }
});

// GET /api/process/:submissionId/status
router.get('/:submissionId/status', authMiddleware, async (req, res) => {
  try {
    const submission = await Submission.findOne({
      _id: req.params.submissionId,
      userId: req.user._id
    });

    if (!submission) {
      return res.status(404).json({ error: 'Submission not found' });
    }

    const response = {
      status: submission.status,
      submissionId: submission._id
    };

    if (submission.status === 'completed') {
      const result = await Result.findOne({ submissionId: submission._id });
      if (result) {
        response.resultId = result._id;
      }
    }

    if (submission.status === 'failed') {
      response.error = submission.errorMessage;
    }

    res.json(response);
  } catch (error) {
    res.status(500).json({ error: 'Failed to check status' });
  }
});


/**
 * Background processing pipeline:
 * OCR → Segment → Align → Grade → Aggregate → Store
 * 
 * If enhanced model answer data is available (with contentTypes, keywords, diagramData),
 * uses the Python-based segmentation engine for intelligent question mapping.
 * Otherwise falls back to the legacy matchAnswers approach.
 */
async function processSubmission(submission) {
  try {
    console.log(`[Pipeline] ================================`);
    console.log(`[Pipeline] Started for submission ${submission._id}`);
    console.log(`[Pipeline] File: ${submission.filePath}`);
    console.log(`[Pipeline] Student: ${submission.studentName || 'N/A'}`);

    // Get model answers — either from EvalSet or from submission itself
    let parsedModelAnswers = submission.parsedModelAnswers;
    let modelStructure = null;
    let pipelineMode = 'legacy';

    if (submission.setId) {
      const evalSet = await EvalSet.findById(submission.setId);
      if (evalSet && evalSet.parsedModelAnswers.length > 0) {
        parsedModelAnswers = evalSet.parsedModelAnswers;
        modelStructure = evalSet.modelStructure;
        console.log(`[Pipeline] Using model answers from set: ${evalSet.setName}`);
        console.log(`[Pipeline] Processing mode: ${evalSet.processingMode || 'regex'}`);
        if (evalSet.processingMode && evalSet.processingMode !== 'regex') {
          pipelineMode = 'enhanced';
        }
      }
    }

    if (!parsedModelAnswers || parsedModelAnswers.length === 0) {
      throw new Error('No model answers available for grading');
    }

    // Check if we have enriched model answer data
    const hasEnrichedData = parsedModelAnswers.some(
      ma => (ma.contentTypes && ma.contentTypes.length > 0) ||
            (ma.keywords && ma.keywords.length > 0)
    );
    if (hasEnrichedData) {
      pipelineMode = 'enhanced';
      console.log(`[Pipeline] Enriched model answer data detected — using enhanced pipeline`);
    }

    console.log(`[Pipeline] Model answers: ${parsedModelAnswers.length} questions`);
    console.log(`[Pipeline] Pipeline mode: ${pipelineMode}`);

    // Step 1: OCR
    console.log('[Pipeline] Step 1: Running OCR...');
    const outputDir = path.join(
      path.dirname(submission.filePath),
      `ocr_output_${submission._id}`
    );
    fs.mkdirSync(outputDir, { recursive: true });

    const ocrResult = await runOCR(submission.filePath, outputDir);

    // Store extracted text
    submission.extractedText = ocrResult.full_text || '';
    submission.structuredAnswers = (ocrResult.structured_answers || []).map(sa => ({
      questionNumber: sa.question_number,
      subtype: sa.subtype || '',
      questionText: sa.question_text || '',
      answerText: sa.answer_text || ''
    }));
    await submission.save();

    console.log(`[Pipeline] OCR extracted text: ${(ocrResult.full_text || '').length} chars`);
    console.log(`[Pipeline] OCR structured answers: ${submission.structuredAnswers.length}`);

    if (ocrResult.warning) {
      console.warn(`[Pipeline] OCR warning: ${ocrResult.warning}`);
    }

    // If structured answers are empty but we have full text, create a fallback
    if (submission.structuredAnswers.length === 0 && ocrResult.full_text) {
      console.log('[Pipeline] No structured answers, using full text as fallback for Q1');
      submission.structuredAnswers = [{
        questionNumber: '1',
        subtype: '',
        questionText: '',
        answerText: ocrResult.full_text
      }];
      await submission.save();
    }

    // Step 2: Segmentation + Alignment (or legacy matching)
    let gradingInput;
    let alignmentSummary = null;

    if (pipelineMode === 'enhanced') {
      console.log('[Pipeline] Step 2: Running enhanced segmentation + alignment...');
      try {
        gradingInput = await runEnhancedSegmentation(
          ocrResult, parsedModelAnswers, modelStructure, outputDir
        );
        alignmentSummary = gradingInput._alignmentSummary;
        delete gradingInput._alignmentSummary;
        gradingInput = gradingInput.items;
        console.log(`[Pipeline] Enhanced segmentation: ${gradingInput.length} grading pairs`);
      } catch (segErr) {
        console.error('[Pipeline] Enhanced segmentation failed, falling back to legacy:', segErr.message);
        pipelineMode = 'legacy';
        gradingInput = buildLegacyGradingInput(submission.structuredAnswers, parsedModelAnswers);
      }
    } else {
      console.log('[Pipeline] Step 2: Legacy answer matching...');
      gradingInput = buildLegacyGradingInput(submission.structuredAnswers, parsedModelAnswers);
    }

    console.log(`[Pipeline] ${gradingInput.length} question pairs ready for grading`);

    // Step 3: Run grader
    console.log('[Pipeline] Step 3: Grading answers...');
    let gradingResults;
    try {
      gradingResults = await runGrader(gradingInput);
    } catch (graderError) {
      console.error('[Pipeline] Grader error:', graderError.message);
      // Fallback: assign 0 marks with error
      gradingResults = gradingInput.map(pair => ({
        question_number: pair.question_number,
        marks_awarded: 0,
        max_marks: pair.max_marks,
        final_score: 0,
        details: {},
        diagram_score: null,
        math_score: null,
        feedback: 'Grading failed: ' + graderError.message,
        content_types_evaluated: [],
        error: graderError.message
      }));
    }

    // Step 4: Aggregate results
    console.log('[Pipeline] Step 4: Aggregating results...');

    const questions = gradingInput.map((pair, idx) => {
      const gradeResult = gradingResults[idx] || {};

      return {
        questionNumber: pair.question_number,
        studentAnswer: pair.student_answer,
        modelAnswer: pair.model_answer,
        type: pair.type,
        maxMarks: pair.max_marks,
        marksAwarded: gradeResult.marks_awarded || 0,
        finalScore: gradeResult.final_score || 0,
        details: gradeResult.details || {},
        feedback: gradeResult.feedback || generateFeedback(gradeResult, pair.type),
        // Enhanced multimodal fields
        contentTypes: pair.content_types || ['text'],
        diagramScore: gradeResult.diagram_score ?? null,
        mathScore: gradeResult.math_score ?? null,
        alignmentConfidence: pair.alignment_confidence ?? null,
        contentTypesEvaluated: gradeResult.content_types_evaluated || []
      };
    });

    const totalMarksAwarded = questions.reduce((sum, q) => sum + q.marksAwarded, 0);
    const totalMaxMarks = questions.reduce((sum, q) => sum + q.maxMarks, 0);
    const percentage = totalMaxMarks > 0 ? Math.round((totalMarksAwarded / totalMaxMarks) * 100) : 0;

    // Step 5: Store result
    const resultData = {
      submissionId: submission._id,
      userId: submission.userId,
      questions,
      totalMarksAwarded,
      totalMaxMarks,
      percentage,
      pipelineMode,
      alignmentSummary
    };

    // Add set and student info if available
    if (submission.setId) {
      resultData.setId = submission.setId;
    }
    if (submission.studentName) {
      resultData.studentName = submission.studentName;
    }

    const result = await Result.create(resultData);

    // Update submission status
    submission.status = 'completed';
    await submission.save();

    console.log(`[Pipeline] ================================`);
    console.log(`[Pipeline] Completed. Score: ${totalMarksAwarded}/${totalMaxMarks} (${percentage}%)`);
    console.log(`[Pipeline] Pipeline mode: ${pipelineMode}`);

  } catch (error) {
    console.error(`[Pipeline] Failed for submission ${submission._id}:`, error);
    submission.status = 'failed';
    submission.errorMessage = error.message;
    await submission.save();
  }
}


/**
 * Run enhanced segmentation + alignment pipeline.
 * Writes OCR result and model structure to temp files, calls Python segmentation engine.
 */
async function runEnhancedSegmentation(ocrResult, parsedModelAnswers, modelStructure, outputDir) {
  // Build model structure if not already available
  if (!modelStructure) {
    modelStructure = {
      questions: {},
      question_structure: [],
      total_marks: 0
    };

    for (const ma of parsedModelAnswers) {
      const qNum = ma.questionNumber;
      modelStructure.questions[qNum] = {
        text: ma.modelAnswer,
        keywords: ma.keywords || [],
        content_types: ma.contentTypes || ['text'],
        diagram: ma.diagramData || null,
        math_expressions: ma.mathExpressions || [],
        marks: ma.maxMarks,
        type: ma.type
      };
      modelStructure.question_structure.push(qNum);
      modelStructure.total_marks += (ma.maxMarks || 0);
    }
  }

  // Write temp files for Python bridge
  const ocrResultPath = path.join(outputDir, 'student_ocr.json');
  const modelStructPath = path.join(outputDir, 'model_structure.json');

  fs.writeFileSync(ocrResultPath, JSON.stringify(ocrResult, null, 2));
  fs.writeFileSync(modelStructPath, JSON.stringify(modelStructure, null, 2));

  // Run segmentation
  const segResult = await runSegmentation(ocrResultPath, modelStructPath, outputDir);

  // Convert to grading input format
  const gradingPairs = (segResult.grading_input || []).map(gi => ({
    question_number: gi.question_number,
    type: gi.type,
    student_answer: gi.student_answer,
    model_answer: gi.model_answer,
    max_marks: gi.max_marks,
    keywords: gi.keywords,
    content_types: gi.content_types,
    diagram_data: gi.diagram_data,
    math_expressions: gi.math_expressions,
    alignment_confidence: gi.alignment_confidence
  }));

  return {
    items: gradingPairs,
    _alignmentSummary: segResult.alignment?.summary || null
  };
}


/**
 * Build grading input from legacy matchAnswers pathway.
 * Used when model answer is .txt or enhanced segmentation is unavailable.
 */
function buildLegacyGradingInput(structuredAnswers, parsedModelAnswers) {
  const matchedPairs = matchAnswers(structuredAnswers, parsedModelAnswers);

  return matchedPairs.map(pair => ({
    question_number: pair.questionNumber,
    type: pair.type,
    student_answer: pair.studentAnswer,
    model_answer: pair.modelAnswer,
    max_marks: pair.maxMarks,
    content_types: pair.contentTypes || ['text'],
    keywords: pair.keywords || {}
  }));
}


module.exports = router;
