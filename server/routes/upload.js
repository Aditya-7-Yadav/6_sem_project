const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const authMiddleware = require('../middleware/auth');
const Submission = require('../models/Submission');
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
  limits: { fileSize: 50 * 1024 * 1024 } // 50MB limit
});

// POST /api/upload
// Fields: answerSheet (required), modelAnswer (required)
router.post('/',
  authMiddleware,
  upload.fields([
    { name: 'answerSheet', maxCount: 1 },
    { name: 'modelAnswer', maxCount: 1 }
  ]),
  async (req, res) => {
    try {
      if (!req.files?.answerSheet?.[0]) {
        return res.status(400).json({ error: 'Answer sheet file is required' });
      }
      if (!req.files?.modelAnswer?.[0]) {
        return res.status(400).json({ error: 'Model answer file is required' });
      }

      const answerSheetFile = req.files.answerSheet[0];
      const modelAnswerFile = req.files.modelAnswer[0];

      // Parse model answer file to extract questions, marks, and answers
      let parsedModelAnswers;
      try {
        parsedModelAnswers = await parseModelAnswerFile(modelAnswerFile.path);
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
      const modelAnswerText = fs.readFileSync(modelAnswerFile.path, 'utf-8');

      // Create submission
      const submission = await Submission.create({
        userId: req.user._id,
        originalFileName: answerSheetFile.originalname,
        filePath: answerSheetFile.path,
        modelAnswerPath: modelAnswerFile.path,
        modelAnswerText: modelAnswerText,
        parsedModelAnswers: parsedModelAnswers,
        status: 'pending'
      });

      res.status(201).json({
        message: 'Files uploaded successfully',
        submission: {
          id: submission._id,
          fileName: submission.originalFileName,
          status: submission.status,
          questionsFound: parsedModelAnswers.length,
          totalMaxMarks: parsedModelAnswers.reduce((sum, q) => sum + q.maxMarks, 0),
          createdAt: submission.createdAt
        }
      });

    } catch (error) {
      console.error('Upload error:', error);
      res.status(500).json({ error: 'Upload failed: ' + error.message });
    }
  }
);

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
