const express = require('express');
const authMiddleware = require('../middleware/auth');
const Submission = require('../models/Submission');
const Result = require('../models/Result');

const router = express.Router();

// GET /api/results — List all results for current user
router.get('/', authMiddleware, async (req, res) => {
  try {
    const results = await Result.find({ userId: req.user._id })
      .populate('submissionId', 'originalFileName status createdAt')
      .sort({ createdAt: -1 });

    const formatted = results.map(r => ({
      id: r._id,
      submissionId: r.submissionId?._id,
      fileName: r.submissionId?.originalFileName || 'Unknown',
      totalMarksAwarded: r.totalMarksAwarded,
      totalMaxMarks: r.totalMaxMarks,
      percentage: r.percentage,
      questionsCount: r.questions.length,
      createdAt: r.createdAt
    }));

    res.json({ results: formatted });
  } catch (error) {
    console.error('Results list error:', error);
    res.status(500).json({ error: 'Failed to fetch results' });
  }
});

// GET /api/results/:id — Detailed result
router.get('/:id', authMiddleware, async (req, res) => {
  try {
    const result = await Result.findOne({
      _id: req.params.id,
      userId: req.user._id
    }).populate('submissionId', 'originalFileName status extractedText createdAt');

    if (!result) {
      return res.status(404).json({ error: 'Result not found' });
    }

    res.json({
      result: {
        id: result._id,
        submission: {
          id: result.submissionId?._id,
          fileName: result.submissionId?.originalFileName,
          extractedText: result.submissionId?.extractedText
        },
        questions: result.questions,
        totalMarksAwarded: result.totalMarksAwarded,
        totalMaxMarks: result.totalMaxMarks,
        percentage: result.percentage,
        createdAt: result.createdAt
      }
    });
  } catch (error) {
    console.error('Result detail error:', error);
    res.status(500).json({ error: 'Failed to fetch result' });
  }
});

// GET /api/results/submission/:submissionId — Result by submission ID
router.get('/submission/:submissionId', authMiddleware, async (req, res) => {
  try {
    const result = await Result.findOne({
      submissionId: req.params.submissionId,
      userId: req.user._id
    }).populate('submissionId', 'originalFileName status extractedText createdAt');

    if (!result) {
      return res.status(404).json({ error: 'Result not found for this submission' });
    }

    res.json({
      result: {
        id: result._id,
        submission: {
          id: result.submissionId?._id,
          fileName: result.submissionId?.originalFileName,
          extractedText: result.submissionId?.extractedText
        },
        questions: result.questions,
        totalMarksAwarded: result.totalMarksAwarded,
        totalMaxMarks: result.totalMaxMarks,
        percentage: result.percentage,
        createdAt: result.createdAt
      }
    });
  } catch (error) {
    console.error('Result by submission error:', error);
    res.status(500).json({ error: 'Failed to fetch result' });
  }
});

// GET /api/results/stats/overview — Dashboard stats
router.get('/stats/overview', authMiddleware, async (req, res) => {
  try {
    const totalSubmissions = await Submission.countDocuments({ userId: req.user._id });
    const completedSubmissions = await Submission.countDocuments({
      userId: req.user._id,
      status: 'completed'
    });
    const pendingSubmissions = await Submission.countDocuments({
      userId: req.user._id,
      status: { $in: ['pending', 'processing'] }
    });

    const results = await Result.find({ userId: req.user._id });
    const avgPercentage = results.length > 0
      ? Math.round(results.reduce((sum, r) => sum + r.percentage, 0) / results.length)
      : 0;

    const recentResults = await Result.find({ userId: req.user._id })
      .populate('submissionId', 'originalFileName createdAt')
      .sort({ createdAt: -1 })
      .limit(5);

    res.json({
      stats: {
        totalSubmissions,
        completedSubmissions,
        pendingSubmissions,
        averageScore: avgPercentage,
        totalEvaluated: results.length
      },
      recentResults: recentResults.map(r => ({
        id: r._id,
        fileName: r.submissionId?.originalFileName || 'Unknown',
        percentage: r.percentage,
        totalMarksAwarded: r.totalMarksAwarded,
        totalMaxMarks: r.totalMaxMarks,
        createdAt: r.createdAt
      }))
    });
  } catch (error) {
    console.error('Stats error:', error);
    res.status(500).json({ error: 'Failed to fetch stats' });
  }
});

module.exports = router;
