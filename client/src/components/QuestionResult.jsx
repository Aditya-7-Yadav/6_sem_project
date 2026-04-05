import { motion } from 'framer-motion';

function getScoreColor(pct) {
  if (pct >= 80) return 'var(--success)';
  if (pct >= 60) return 'var(--accent-light)';
  if (pct >= 40) return 'var(--warning)';
  return 'var(--error)';
}

export default function QuestionResult({ question, index }) {
  const pct = question.maxMarks > 0
    ? (question.marksAwarded / question.maxMarks) * 100
    : 0;
  const color = getScoreColor(pct);

  return (
    <motion.div
      className="question-card glass-card"
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.08, duration: 0.4 }}
    >
      <div className="question-header">
        <div className="question-number">
          <h3>Question {question.questionNumber}</h3>
          <span className={`question-badge ${question.type}`}>
            {question.type === 'short' ? 'Short' : 'Long'}
          </span>
        </div>
        <motion.div
          className="question-score-badge"
          style={{ background: `${color}22`, color }}
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ delay: index * 0.08 + 0.3, type: 'spring' }}
        >
          {question.marksAwarded} / {question.maxMarks}
        </motion.div>
      </div>

      <div className="question-score-bar">
        <motion.div
          className="question-score-bar-fill"
          style={{ background: color }}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ delay: index * 0.08 + 0.2, duration: 0.8, ease: 'easeOut' }}
        />
      </div>

      <div className="question-content">
        <div className="question-answer-block">
          <div className="question-answer-label">Student Answer</div>
          <div className="question-answer-text">
            {question.studentAnswer || <em style={{ color: 'var(--text-muted)' }}>No answer provided</em>}
          </div>
        </div>
        <div className="question-answer-block">
          <div className="question-answer-label">Model Answer</div>
          <div className="question-answer-text">{question.modelAnswer}</div>
        </div>
      </div>

      {question.feedback && (
        <motion.div
          className="question-feedback"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: index * 0.08 + 0.5 }}
        >
          {question.feedback}
        </motion.div>
      )}
    </motion.div>
  );
}
