import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { HiOutlineArrowLeft } from 'react-icons/hi';
import api from '../api';
import QuestionResult from '../components/QuestionResult';

export default function SubmissionDetail() {
  const { id } = useParams();
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchResult();
  }, [id]);

  const fetchResult = async () => {
    try {
      const res = await api.get(`/api/results/${id}`);
      setResult(res.data.result);
    } catch (err) {
      console.error('Failed to fetch result:', err);
    } finally {
      setLoading(false);
    }
  };

  const getScoreClass = (pct) => {
    if (pct >= 80) return 'score-excellent';
    if (pct >= 60) return 'score-good';
    if (pct >= 40) return 'score-average';
    return 'score-poor';
  };

  const getGradeLabel = (pct) => {
    if (pct >= 90) return 'Outstanding';
    if (pct >= 80) return 'Excellent';
    if (pct >= 70) return 'Very Good';
    if (pct >= 60) return 'Good';
    if (pct >= 50) return 'Average';
    if (pct >= 40) return 'Below Average';
    return 'Needs Improvement';
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '4rem' }}>
        <div className="loader-ring"><div></div><div></div><div></div><div></div></div>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">❌</div>
        <h2 className="empty-state-title">Result Not Found</h2>
        <Link to="/results" className="btn btn-primary">Back to Results</Link>
      </div>
    );
  }

  const shortCount = result.questions.filter(q => q.type === 'short').length;
  const longCount = result.questions.filter(q => q.type === 'long').length;

  return (
    <div>
      {/* Back button */}
      <motion.div
        initial={{ opacity: 0, x: -10 }}
        animate={{ opacity: 1, x: 0 }}
        style={{ marginBottom: '1.5rem' }}
      >
        <Link to="/results" className="btn btn-secondary" id="back-to-results">
          <HiOutlineArrowLeft /> Back to Results
        </Link>
      </motion.div>

      {/* Header */}
      <div className="detail-header">
        <div>
          <motion.h1
            className="page-title"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            style={{ fontSize: '1.75rem' }}
          >
            {result.submission?.fileName || 'Evaluation Result'}
          </motion.h1>
          <motion.p
            className="page-subtitle"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.1 }}
          >
            Evaluated on {new Date(result.createdAt).toLocaleDateString('en-US', {
              year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit'
            })}
          </motion.p>
        </div>
      </div>

      {/* Score Summary */}
      <motion.div
        className="score-summary glass-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
      >
        <div className="score-circle">
          <motion.span
            className="score-circle-value"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
          >
            {result.percentage}%
          </motion.span>
          <span className="score-circle-label">{getGradeLabel(result.percentage)}</span>
        </div>
        <div className="score-stats">
          <div>
            <div className="score-stat-value">{result.totalMarksAwarded}</div>
            <div className="score-stat-label">Marks Obtained</div>
          </div>
          <div>
            <div className="score-stat-value">{result.totalMaxMarks}</div>
            <div className="score-stat-label">Total Marks</div>
          </div>
          <div>
            <div className="score-stat-value">{result.questions.length}</div>
            <div className="score-stat-label">Questions</div>
          </div>
          <div>
            <div className="score-stat-value">{shortCount}S / {longCount}L</div>
            <div className="score-stat-label">Short / Long</div>
          </div>
        </div>
      </motion.div>

      {/* Question-wise Results */}
      <motion.h2
        style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '1rem' }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.3 }}
      >
        Question-wise Breakdown
      </motion.h2>

      <div className="questions-list">
        {result.questions.map((question, index) => (
          <QuestionResult key={index} question={question} index={index} />
        ))}
      </div>
    </div>
  );
}
