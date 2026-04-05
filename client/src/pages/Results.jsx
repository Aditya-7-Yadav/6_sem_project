import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { HiOutlineDocumentReport, HiOutlineCloudUpload } from 'react-icons/hi';
import api from '../api';

export default function Results() {
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchResults();
  }, []);

  const fetchResults = async () => {
    try {
      const res = await api.get('/api/results');
      setResults(res.data.results);
    } catch (err) {
      console.error('Failed to fetch results:', err);
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

  return (
    <div>
      <div className="page-header">
        <motion.h1
          className="page-title"
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
        >
          Evaluation Results
        </motion.h1>
        <motion.p
          className="page-subtitle"
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.1 }}
        >
          All your past evaluations and scores
        </motion.p>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '4rem' }}>
          <div className="loader-ring"><div></div><div></div><div></div><div></div></div>
        </div>
      ) : results.length === 0 ? (
        <motion.div
          className="empty-state"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="empty-state-icon">📋</div>
          <h2 className="empty-state-title">No Results Yet</h2>
          <p className="empty-state-text">Upload and evaluate your first answer sheet to see results here</p>
          <Link to="/upload" className="btn btn-primary">
            <HiOutlineCloudUpload /> New Evaluation
          </Link>
        </motion.div>
      ) : (
        <div className="results-list">
          {results.map((item, i) => (
            <motion.div
              key={item.id}
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
            >
              <Link to={`/results/${item.id}`} className="result-card glass-card" id={`result-${item.id}`}>
                <div style={{ marginRight: '1rem', color: 'var(--primary-light)' }}>
                  <HiOutlineDocumentReport size={28} />
                </div>
                <div className="result-card-info">
                  <div className="result-card-filename">{item.fileName}</div>
                  <div className="result-card-meta">
                    <span>{new Date(item.createdAt).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}</span>
                    <span>{item.questionsCount} questions</span>
                    <span>{item.totalMarksAwarded}/{item.totalMaxMarks} marks</span>
                  </div>
                </div>
                <div className="result-card-score">
                  <span className={`result-card-percentage ${getScoreClass(item.percentage)}`}>
                    {item.percentage}%
                  </span>
                  <span className="result-card-marks">
                    {item.totalMarksAwarded}/{item.totalMaxMarks}
                  </span>
                </div>
              </Link>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
