import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { HiOutlineCollection, HiOutlineDocumentReport, HiOutlineCheckCircle, HiOutlineClock, HiOutlineChartBar, HiOutlineTrendingUp, HiOutlinePlusCircle } from 'react-icons/hi';
import api from '../api';
import ScoreCard from '../components/ScoreCard';

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [recent, setRecent] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    try {
      const res = await api.get('/api/results/stats/overview');
      setStats(res.data.stats);
      setRecent(res.data.recentResults);
    } catch (err) {
      console.error('Failed to fetch stats:', err);
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
          Dashboard
        </motion.h1>
        <motion.p
          className="page-subtitle"
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.1 }}
        >
          Overview of your evaluations and activity
        </motion.p>
      </div>

      <div className="stats-grid">
        <ScoreCard
          icon={<HiOutlineDocumentReport />}
          value={stats?.totalSubmissions ?? '—'}
          label="Total Submissions"
          color="purple"
        />
        <ScoreCard
          icon={<HiOutlineCheckCircle />}
          value={stats?.completedSubmissions ?? '—'}
          label="Evaluated"
          color="green"
        />
        <ScoreCard
          icon={<HiOutlineClock />}
          value={stats?.pendingSubmissions ?? '—'}
          label="Pending"
          color="amber"
        />
        <ScoreCard
          icon={<HiOutlineTrendingUp />}
          value={stats?.averageScore != null ? `${stats.averageScore}%` : '—'}
          label="Average Score"
          color="cyan"
        />
      </div>

      {/* Quick Actions */}
      <motion.div
        style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
      >
        <Link to="/sets/create" style={{ textDecoration: 'none' }}>
          <motion.div className="glass-card" style={{ padding: '2rem', cursor: 'pointer' }} whileHover={{ y: -4 }}>
            <HiOutlinePlusCircle style={{ fontSize: '2rem', color: 'var(--primary-light)', marginBottom: '0.75rem' }} />
            <h3 style={{ fontWeight: 700, marginBottom: '0.5rem' }}>Create Evaluation Set</h3>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Upload model answer and evaluate multiple students</p>
          </motion.div>
        </Link>
        <Link to="/sets" style={{ textDecoration: 'none' }}>
          <motion.div className="glass-card" style={{ padding: '2rem', cursor: 'pointer' }} whileHover={{ y: -4 }}>
            <HiOutlineCollection style={{ fontSize: '2rem', color: 'var(--accent-light)', marginBottom: '0.75rem' }} />
            <h3 style={{ fontWeight: 700, marginBottom: '0.5rem' }}>View Eval Sets</h3>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Browse all evaluation sets and student results</p>
          </motion.div>
        </Link>
        <Link to="/results" style={{ textDecoration: 'none' }}>
          <motion.div className="glass-card" style={{ padding: '2rem', cursor: 'pointer' }} whileHover={{ y: -4 }}>
            <HiOutlineChartBar style={{ fontSize: '2rem', color: 'var(--success)', marginBottom: '0.75rem' }} />
            <h3 style={{ fontWeight: 700, marginBottom: '0.5rem' }}>All Results</h3>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Browse all past evaluation results</p>
          </motion.div>
        </Link>
      </motion.div>

      {/* Recent Results */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
      >
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '1rem' }}>Recent Evaluations</h2>
        {recent.length === 0 ? (
          <div className="glass-card" style={{ padding: '3rem', textAlign: 'center' }}>
            <p style={{ color: 'var(--text-muted)' }}>No evaluations yet. Create an evaluation set to get started!</p>
          </div>
        ) : (
          <div className="results-list">
            {recent.map((item, i) => (
              <motion.div
                key={item.id}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.3 + i * 0.05 }}
              >
                <Link to={`/results/${item.id}`} className="result-card glass-card">
                  <div className="result-card-info">
                    <div className="result-card-filename">{item.fileName}</div>
                    <div className="result-card-meta">
                      <span>{new Date(item.createdAt).toLocaleDateString()}</span>
                      <span>{item.totalMarksAwarded}/{item.totalMaxMarks} marks</span>
                    </div>
                  </div>
                  <div className="result-card-score">
                    <span className={`result-card-percentage ${getScoreClass(item.percentage)}`}>
                      {item.percentage}%
                    </span>
                  </div>
                </Link>
              </motion.div>
            ))}
          </div>
        )}
      </motion.div>
    </div>
  );
}
