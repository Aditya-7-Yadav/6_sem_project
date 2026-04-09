const express = require('express');
const path = require('path');
const fs = require('fs');
const authMiddleware = require('../middleware/auth');
const Submission = require('../models/Submission');
const Result = require('../models/Result');
const EvalSet = require('../models/EvalSet');
const { runOCR, runGrader } = require('../services/pythonBridge');

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
 * OCR → Parse → Match → Classify → Grade → Aggregate → Store
 */
async function processSubmission(submission) {
  try {
    console.log(`[Pipeline] ================================`);
    console.log(`[Pipeline] Started for submission ${submission._id}`);
    console.log(`[Pipeline] File: ${submission.filePath}`);
    console.log(`[Pipeline] Student: ${submission.studentName || 'N/A'}`);

    // Get model answers — either from EvalSet or from submission itself
    let parsedModelAnswers = submission.parsedModelAnswers;

    if (submission.setId) {
      const evalSet = await EvalSet.findById(submission.setId);
      if (evalSet && evalSet.parsedModelAnswers.length > 0) {
        parsedModelAnswers = evalSet.parsedModelAnswers;
        console.log(`[Pipeline] Using model answers from set: ${evalSet.setName}`);
      }
    }

    if (!parsedModelAnswers || parsedModelAnswers.length === 0) {
      throw new Error('No model answers available for grading');
    }

    console.log(`[Pipeline] Model answers: ${parsedModelAnswers.length} questions`);

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

    // Step 2: Match student answers to model answers
    console.log('[Pipeline] Step 2: Matching answers...');
    const matchedPairs = matchAnswers(
      submission.structuredAnswers,
      parsedModelAnswers
    );

    console.log(`[Pipeline] Matched ${matchedPairs.length} question pairs`);

    // Step 3: Prepare grading input
    console.log('[Pipeline] Step 3: Grading answers...');
    const gradingInput = matchedPairs.map(pair => ({
      question_number: pair.questionNumber,
      type: pair.type,
      student_answer: pair.studentAnswer,
      model_answer: pair.modelAnswer,
      max_marks: pair.maxMarks
    }));

    // Step 4: Run grader
    let gradingResults;
    try {
      gradingResults = await runGrader(gradingInput);
    } catch (graderError) {
      console.error('[Pipeline] Grader error:', graderError.message);
      // Fallback: assign 0 marks with error
      gradingResults = matchedPairs.map(pair => ({
        question_number: pair.questionNumber,
        marks_awarded: 0,
        max_marks: pair.maxMarks,
        final_score: 0,
        details: {},
        error: graderError.message
      }));
    }

    // Step 5: Aggregate results
    console.log('[Pipeline] Step 5: Aggregating results...');

    const questions = matchedPairs.map((pair, idx) => {
      const gradeResult = gradingResults[idx] || {};

      return {
        questionNumber: pair.questionNumber,
        studentAnswer: pair.studentAnswer,
        modelAnswer: pair.modelAnswer,
        type: pair.type,
        maxMarks: pair.maxMarks,
        marksAwarded: gradeResult.marks_awarded || 0,
        finalScore: gradeResult.final_score || 0,
        details: gradeResult.details || {},
        feedback: generateFeedback(gradeResult, pair.type)
      };
    });

    const totalMarksAwarded = questions.reduce((sum, q) => sum + q.marksAwarded, 0);
    const totalMaxMarks = questions.reduce((sum, q) => sum + q.maxMarks, 0);
    const percentage = totalMaxMarks > 0 ? Math.round((totalMarksAwarded / totalMaxMarks) * 100) : 0;

    // Step 6: Store result
    const resultData = {
      submissionId: submission._id,
      userId: submission.userId,
      questions,
      totalMarksAwarded,
      totalMaxMarks,
      percentage
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

  } catch (error) {
    console.error(`[Pipeline] Failed for submission ${submission._id}:`, error);
    submission.status = 'failed';
    submission.errorMessage = error.message;
    await submission.save();
  }
}

module.exports = router;
