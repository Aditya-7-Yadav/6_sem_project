const mongoose = require('mongoose');

const evalSetSchema = new mongoose.Schema({
  userId: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    required: true
  },
  setName: {
    type: String,
    required: true,
    trim: true
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
  }]
}, {
  timestamps: true
});

module.exports = mongoose.model('EvalSet', evalSetSchema);
