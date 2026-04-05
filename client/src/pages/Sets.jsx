import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { HiOutlineCollection, HiOutlinePlusCircle, HiOutlineDocumentReport, HiOutlineUserGroup, HiOutlineTrendingUp } from 'react-icons/hi';
import api from '../api';

export default function Sets() {
  const [sets, setSets] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSets();
  }, []);

  const fetchSets = async () => {
    try {
      const res = await api.get('/api/sets');
      setSets(res.data.sets);
    } catch (err) {
      console.error('Failed to fetch sets:', err);
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
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <motion.h1
            className="page-title"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
          >
            Evaluation Sets
          </motion.h1>
          <motion.p
            className="page-subtitle"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.1 }}
          >
            Create sets, upload model answers once, then evaluate multiple students
          </motion.p>
        </div>
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.15 }}
        >
          <Link to="/sets/create" className="btn btn-primary" id="create-set-btn">
            <HiOutlinePlusCircle /> Create New Set
          </Link>
        </motion.div>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '4rem' }}>
          <div className="loader-ring"><div></div><div></div><div></div><div></div></div>
        </div>
      ) : sets.length === 0 ? (
        <motion.div
          className="empty-state"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div style={{ fontSize: '4rem', marginBottom: '1rem', opacity: 0.3 }}>📚</div>
          <h2 className="empty-state-title">No Evaluation Sets Yet</h2>
          <p className="empty-state-text">Create your first evaluation set to start grading student answer sheets</p>
          <Link to="/sets/create" className="btn btn-primary">
            <HiOutlinePlusCircle /> Create First Set
          </Link>
        </motion.div>
      ) : (
        <div className="sets-grid">
          {sets.map((set, i) => (
            <motion.div
              key={set.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.06 }}
            >
              <Link to={`/sets/${set.id}`} className="set-card glass-card" id={`set-${set.id}`}>
                <div className="set-card-header">
                  <div className="set-card-name">{set.setName}</div>
                  <div className="set-card-date">
                    {new Date(set.createdAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  </div>
                </div>

                <div className="set-card-stats">
                  <div className="set-card-stat">
                    <div className="set-card-stat-value">{set.questionsCount}</div>
                    <div className="set-card-stat-label">Questions</div>
                  </div>
                  <div className="set-card-stat">
                    <div className="set-card-stat-value">{set.submissionCount}</div>
                    <div className="set-card-stat-label">Students</div>
                  </div>
                  <div className="set-card-stat">
                    <div className={`set-card-stat-value ${set.averageScore > 0 ? getScoreClass(set.averageScore) : ''}`}>
                      {set.averageScore > 0 ? `${set.averageScore}%` : '—'}
                    </div>
                    <div className="set-card-stat-label">Avg Score</div>
                  </div>
                </div>

                <div className="set-card-footer">
                  <div className="set-card-badge">
                    <HiOutlineDocumentReport /> {set.totalMaxMarks} marks
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    {set.completedCount}/{set.submissionCount} evaluated
                  </div>
                </div>
              </Link>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
