const mongoose = require('mongoose');

const questionResultSchema = new mongoose.Schema({
  questionNumber: String,
  studentAnswer: String,
  modelAnswer: String,
  type: { type: String, enum: ['short', 'long'] },
  maxMarks: Number,
  marksAwarded: Number,
  finalScore: Number,
  details: mongoose.Schema.Types.Mixed,
  feedback: String
}, { _id: false });

const resultSchema = new mongoose.Schema({
  submissionId: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'Submission',
    required: true
  },
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
  questions: [questionResultSchema],
  totalMarksAwarded: {
    type: Number,
    default: 0
  },
  totalMaxMarks: {
    type: Number,
    default: 0
  },
  percentage: {
    type: Number,
    default: 0
  }
}, {
  timestamps: true
});

module.exports = mongoose.model('Result', resultSchema);
