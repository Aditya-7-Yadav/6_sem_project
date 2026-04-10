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
    type: { type: String, enum: ['short', 'long'] },
    // Enhanced fields for multimodal evaluation
    contentTypes: { type: [String], default: ['text'] },   // ['text', 'diagram', 'numerical', 'theorem']
    keywords: { type: [String], default: [] },              // extracted key concepts
    diagramData: { type: mongoose.Schema.Types.Mixed, default: null },  // structured diagram description
    mathExpressions: { type: [String], default: [] }        // expected math expressions
  }],
  // Model answer structure metadata
  modelStructure: {
    type: mongoose.Schema.Types.Mixed,
    default: null
  },
  processingMode: {
    type: String,
    default: 'regex'   // 'regex' | 'gemini' | 'gemini_vision'
  }
}, {
  timestamps: true
});

module.exports = mongoose.model('EvalSet', evalSetSchema);

