const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const authMiddleware = require('../middleware/auth');
const EvalSet = require('../models/EvalSet');
const Submission = require('../models/Submission');
const Result = require('../models/Result');
const { parseModelAnswerFile } = require('../utils/fileConverter');

const router = express.Router();

// Configure multer storage
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    const uploadDir = path.join(__dirname, '..', '..', 'uploads', req.user._id.toString());
    fs.mkdirSync(uploadDir, { recursive: true });
    cb(null, uploadDir);
  },
  filename: (req, file, cb) => {
    const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
    cb(null, uniqueSuffix + path.extname(file.originalname));
  }
});

const fileFilter = (req, file, cb) => {
  const allowedTypes = [
    'application/pdf',
    'image/jpeg',
    'image/png',
    'image/bmp',
    'image/tiff',
    'text/plain'
  ];
  if (allowedTypes.includes(file.mimetype)) {
    cb(null, true);
  } else {
    cb(new Error(`Unsupported file type: ${file.mimetype}`), false);
  }
};

const upload = multer({
  storage,
  fileFilter,
  limits: { fileSize: 50 * 1024 * 1024 }
});

// ===================== DELETE STUDENT SUBMISSION =====================
// DELETE /api/sets/submission/:subId
router.delete('/submission/:subId', authMiddleware, async (req, res) => {
  try {
    const submission = await Submission.findOne({
      _id: req.params.subId,
      userId: req.user._id
    });

    if (!submission) {
      return res.status(404).json({ error: 'Submission not found' });
    }

    // Delete associated result
    await Result.deleteMany({ submissionId: submission._id });

    // Delete the uploaded file
    if (submission.filePath && fs.existsSync(submission.filePath)) {
      fs.unlinkSync(submission.filePath);
    }

    await Submission.deleteOne({ _id: submission._id });

    res.json({ message: 'Student submission deleted' });
  } catch (error) {
    console.error('Delete submission error:', error);
    res.status(500).json({ error: 'Failed to delete submission' });
  }
});

// ===================== UPDATE STUDENT SUBMISSION =====================
// PUT /api/sets/submission/:subId — Update student name or re-upload file
router.put('/submission/:subId',
  authMiddleware,
  upload.single('answerSheet'),
  async (req, res) => {
    try {
      const submission = await Submission.findOne({
        _id: req.params.subId,
        userId: req.user._id
      });

      if (!submission) {
        return res.status(404).json({ error: 'Submission not found' });
      }

      // Update student name if provided
      if (req.body.studentName && req.body.studentName.trim()) {
        submission.studentName = req.body.studentName.trim();
      }

      // Re-upload file if provided
      if (req.file) {
        // Delete old file
        if (submission.filePath && fs.existsSync(submission.filePath)) {
          fs.unlinkSync(submission.filePath);
        }
        submission.filePath = req.file.path;
        submission.originalFileName = req.file.originalname;

        // Reset status so it can be re-processed
        submission.status = 'pending';
        submission.extractedText = '';
        submission.structuredAnswers = [];
        submission.errorMessage = '';

        // Delete old result
        await Result.deleteMany({ submissionId: submission._id });
      }

      await submission.save();

      // Update student name in result too (if exists and only name changed)
      if (!req.file && req.body.studentName) {
        await Result.updateMany(
          { submissionId: submission._id },
          { studentName: submission.studentName }
        );
      }

      res.json({
        message: 'Submission updated',
        submission: {
          id: submission._id,
          studentName: submission.studentName,
          originalFileName: submission.originalFileName,
          status: submission.status
        }
      });
    } catch (error) {
      console.error('Update submission error:', error);
      res.status(500).json({ error: 'Failed to update submission: ' + error.message });
    }
  }
);

// ===================== CREATE SET =====================
// POST /api/sets — Create a new evaluation set with model answer
router.post('/',
  authMiddleware,
  upload.single('modelAnswer'),
  async (req, res) => {
    try {
      const { setName } = req.body;

      if (!setName || !setName.trim()) {
        return res.status(400).json({ error: 'Set name is required' });
      }

      if (!req.file) {
        return res.status(400).json({ error: 'Model answer file is required' });
      }

      // Parse model answer file
      let parsedModelAnswers;
      try {
        parsedModelAnswers = await parseModelAnswerFile(req.file.path);
      } catch (err) {
        return res.status(400).json({
          error: `Failed to parse model answer file: ${err.message}`,
          hint: 'Model answer file should follow the format: Q1 [2 marks]\\nAnswer text...'
        });
      }

      if (!parsedModelAnswers || parsedModelAnswers.length === 0) {
        return res.status(400).json({
          error: 'No questions found in model answer file',
          hint: 'Each question should start with Q<number> [<marks>] or <number>. [<marks>]'
        });
      }

      // Read model answer text
      let modelAnswerText = '';
      try {
        modelAnswerText = fs.readFileSync(req.file.path, 'utf-8');
      } catch {
        // For PDFs, text was already extracted by parseModelAnswerFile
      }

      const evalSet = await EvalSet.create({
        userId: req.user._id,
        setName: setName.trim(),
        modelAnswerPath: req.file.path,
        modelAnswerText,
        parsedModelAnswers
      });

      const totalMaxMarks = parsedModelAnswers.reduce((sum, q) => sum + q.maxMarks, 0);

      res.status(201).json({
        message: 'Evaluation set created successfully',
        set: {
          id: evalSet._id,
          setName: evalSet.setName,
          questionsCount: parsedModelAnswers.length,
          totalMaxMarks,
          createdAt: evalSet.createdAt
        }
      });

    } catch (error) {
      console.error('Create set error:', error);
      res.status(500).json({ error: 'Failed to create set: ' + error.message });
    }
  }
);

// ===================== LIST SETS =====================
// GET /api/sets — List all sets for current user
router.get('/', authMiddleware, async (req, res) => {
  try {
    const sets = await EvalSet.find({ userId: req.user._id })
      .sort({ createdAt: -1 });

    const setsWithStats = await Promise.all(sets.map(async (s) => {
      const submissionCount = await Submission.countDocuments({ setId: s._id });
      const completedCount = await Submission.countDocuments({ setId: s._id, status: 'completed' });
      const results = await Result.find({ setId: s._id });

      const totalMaxMarks = s.parsedModelAnswers.reduce((sum, q) => sum + q.maxMarks, 0);
      const avgPercentage = results.length > 0
        ? Math.round(results.reduce((sum, r) => sum + r.percentage, 0) / results.length)
        : 0;

      return {
        id: s._id,
        setName: s.setName,
        questionsCount: s.parsedModelAnswers.length,
        totalMaxMarks,
        submissionCount,
        completedCount,
        averageScore: avgPercentage,
        createdAt: s.createdAt
      };
    }));

    res.json({ sets: setsWithStats });
  } catch (error) {
    console.error('List sets error:', error);
    res.status(500).json({ error: 'Failed to fetch sets' });
  }
});

// ===================== GET SET DETAIL =====================
// GET /api/sets/:setId — Get set details with submissions list
router.get('/:setId', authMiddleware, async (req, res) => {
  try {
    const evalSet = await EvalSet.findOne({
      _id: req.params.setId,
      userId: req.user._id
    });

    if (!evalSet) {
      return res.status(404).json({ error: 'Set not found' });
    }

    const submissions = await Submission.find({ setId: evalSet._id })
      .sort({ createdAt: -1 });

    const results = await Result.find({ setId: evalSet._id });

    const totalMaxMarks = evalSet.parsedModelAnswers.reduce((sum, q) => sum + q.maxMarks, 0);

    // Build a map of submissionId -> result
    const resultMap = {};
    for (const r of results) {
      resultMap[r.submissionId.toString()] = {
        resultId: r._id,
        percentage: r.percentage,
        totalMarksAwarded: r.totalMarksAwarded,
        totalMaxMarks: r.totalMaxMarks
      };
    }

    const submissionsList = submissions.map(sub => {
      const result = resultMap[sub._id.toString()];
      return {
        id: sub._id,
        studentName: sub.studentName,
        originalFileName: sub.originalFileName,
        status: sub.status,
        errorMessage: sub.errorMessage,
        result: result || null,
        createdAt: sub.createdAt
      };
    });

    // Chart data: distribution of marks
    const chartData = results.map(r => ({
      studentName: r.studentName || 'Unknown',
      percentage: r.percentage,
      marksAwarded: r.totalMarksAwarded,
      totalMaxMarks: r.totalMaxMarks
    }));

    const avgPercentage = results.length > 0
      ? Math.round(results.reduce((sum, r) => sum + r.percentage, 0) / results.length)
      : 0;

    res.json({
      set: {
        id: evalSet._id,
        setName: evalSet.setName,
        questionsCount: evalSet.parsedModelAnswers.length,
        totalMaxMarks,
        questions: evalSet.parsedModelAnswers.map(q => ({
          questionNumber: q.questionNumber,
          maxMarks: q.maxMarks,
          type: q.type
        })),
        createdAt: evalSet.createdAt
      },
      submissions: submissionsList,
      stats: {
        totalStudents: submissions.length,
        evaluated: results.length,
        pending: submissions.filter(s => ['pending', 'processing'].includes(s.status)).length,
        averageScore: avgPercentage
      },
      chartData
    });
  } catch (error) {
    console.error('Get set detail error:', error);
    res.status(500).json({ error: 'Failed to fetch set details' });
  }
});

// ===================== SUBMIT STUDENT ANSWER =====================
// POST /api/sets/:setId/submit — Upload student answer under a set
router.post('/:setId/submit',
  authMiddleware,
  upload.single('answerSheet'),
  async (req, res) => {
    try {
      const { studentName } = req.body;

      if (!studentName || !studentName.trim()) {
        return res.status(400).json({ error: 'Student name is required' });
      }

      if (!req.file) {
        return res.status(400).json({ error: 'Answer sheet file is required' });
      }

      const evalSet = await EvalSet.findOne({
        _id: req.params.setId,
        userId: req.user._id
      });

      if (!evalSet) {
        return res.status(404).json({ error: 'Set not found' });
      }

      // Create submission linked to the set
      const submission = await Submission.create({
        userId: req.user._id,
        setId: evalSet._id,
        studentName: studentName.trim(),
        originalFileName: req.file.originalname,
        filePath: req.file.path,
        // Model answers come from the set, not stored on submission
        parsedModelAnswers: evalSet.parsedModelAnswers,
        status: 'pending'
      });

      res.status(201).json({
        message: 'Student answer uploaded successfully',
        submission: {
          id: submission._id,
          studentName: submission.studentName,
          fileName: submission.originalFileName,
          status: submission.status,
          createdAt: submission.createdAt
        }
      });

    } catch (error) {
      console.error('Submit student answer error:', error);
      res.status(500).json({ error: 'Failed to upload student answer: ' + error.message });
    }
  }
);

// ===================== DELETE SET =====================
// DELETE /api/sets/:setId
router.delete('/:setId', authMiddleware, async (req, res) => {
  try {
    const evalSet = await EvalSet.findOne({
      _id: req.params.setId,
      userId: req.user._id
    });

    if (!evalSet) {
      return res.status(404).json({ error: 'Set not found' });
    }

    // Delete associated submissions and results
    const submissions = await Submission.find({ setId: evalSet._id });
    const subIds = submissions.map(s => s._id);

    await Result.deleteMany({ submissionId: { $in: subIds } });
    await Submission.deleteMany({ setId: evalSet._id });
    await EvalSet.deleteOne({ _id: evalSet._id });

    res.json({ message: 'Set and all associated data deleted' });
  } catch (error) {
    console.error('Delete set error:', error);
    res.status(500).json({ error: 'Failed to delete set' });
  }
});

// ===================== GET SET RESULTS =====================
// GET /api/sets/:setId/results — Get all results for a set
router.get('/:setId/results', authMiddleware, async (req, res) => {
  try {
    const evalSet = await EvalSet.findOne({
      _id: req.params.setId,
      userId: req.user._id
    });

    if (!evalSet) {
      return res.status(404).json({ error: 'Set not found' });
    }

    const results = await Result.find({ setId: evalSet._id })
      .populate('submissionId', 'originalFileName studentName status createdAt')
      .sort({ createdAt: -1 });

    const formatted = results.map(r => ({
      id: r._id,
      submissionId: r.submissionId?._id,
      studentName: r.studentName || r.submissionId?.studentName || 'Unknown',
      fileName: r.submissionId?.originalFileName || 'Unknown',
      totalMarksAwarded: r.totalMarksAwarded,
      totalMaxMarks: r.totalMaxMarks,
      percentage: r.percentage,
      questionsCount: r.questions.length,
      createdAt: r.createdAt
    }));

    res.json({ results: formatted });
  } catch (error) {
    console.error('Set results error:', error);
    res.status(500).json({ error: 'Failed to fetch set results' });
  }
});

// Error handling for multer
router.use((err, req, res, next) => {
  if (err instanceof multer.MulterError) {
    return res.status(400).json({ error: `Upload error: ${err.message}` });
  }
  if (err) {
    return res.status(400).json({ error: err.message });
  }
  next();
});

module.exports = router;
