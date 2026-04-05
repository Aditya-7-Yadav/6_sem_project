const mongoose = require('mongoose');

const submissionSchema = new mongoose.Schema({
  userId: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    required: true
  },
  setId: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'EvalSet',
    default: null
  },
  studentName: {
    type: String,
    default: ''
  },
  originalFileName: {
    type: String,
    required: true
  },
  filePath: {
    type: String,
    required: true
  },
  modelAnswerPath: {
    type: String,
    default: ''
  },
  modelAnswerText: {
    type: String,
    default: ''
  },
  parsedModelAnswers: [{
    questionNumber: String,
    modelAnswer: String,
    maxMarks: Number,
    type: { type: String, enum: ['short', 'long'] }
  }],
  extractedText: {
    type: String,
    default: ''
  },
  structuredAnswers: [{
    questionNumber: String,
    subtype: String,
    questionText: String,
    answerText: String
  }],
  status: {
    type: String,
    enum: ['pending', 'processing', 'completed', 'failed'],
    default: 'pending'
  },
  errorMessage: {
    type: String,
    default: ''
  }
}, {
  timestamps: true
});

module.exports = mongoose.model('Submission', submissionSchema);
