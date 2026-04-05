import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import toast from 'react-hot-toast';
import {
  HiOutlineArrowLeft, HiOutlineDocumentText, HiOutlineLightningBolt, HiOutlineTrash,
  HiOutlineUserAdd, HiOutlineEye, HiOutlineChartBar, HiOutlineCheckCircle, HiOutlineClock,
  HiOutlinePencil, HiOutlineX, HiOutlineCheck
} from 'react-icons/hi';
import api from '../api';
import FileDropzone from '../components/FileDropzone';

function getScoreClass(pct) {
  if (pct >= 80) return 'score-excellent';
  if (pct >= 60) return 'score-good';
  if (pct >= 40) return 'score-average';
  return 'score-poor';
}

function getBarColor(pct) {
  if (pct >= 80) return 'var(--success)';
  if (pct >= 60) return 'var(--accent)';
  if (pct >= 40) return 'var(--warning)';
  return 'var(--error)';
}

export default function SetDetail() {
  const { setId } = useParams();
  const navigate = useNavigate();
  const [setData, setSetData] = useState(null);
  const [submissions, setSubmissions] = useState([]);
  const [stats, setStats] = useState(null);
  const [chartData, setChartData] = useState([]);
  const [loading, setLoading] = useState(true);

  // Upload form state
  const [studentName, setStudentName] = useState('');
  const [answerSheet, setAnswerSheet] = useState(null);
  const [uploading, setUploading] = useState(false);

  // Edit state
  const [editingId, setEditingId] = useState(null);
  const [editName, setEditName] = useState('');
  const [editFile, setEditFile] = useState(null);
  const [saving, setSaving] = useState(false);

  // Polling
  const pollRef = useRef(null);

  const fetchSetDetail = useCallback(async () => {
    try {
      const res = await api.get(`/api/sets/${setId}`);
      setSetData(res.data.set);
      setSubmissions(res.data.submissions);
      setStats(res.data.stats);
      setChartData(res.data.chartData || []);
    } catch (err) {
      console.error('Failed to fetch set:', err);
      if (err.response?.status === 404) {
        toast.error('Set not found');
        navigate('/sets');
      }
    } finally {
      setLoading(false);
    }
  }, [setId, navigate]);

  useEffect(() => {
    fetchSetDetail();
  }, [fetchSetDetail]);

  // Poll for processing submissions
  useEffect(() => {
    const hasPending = submissions.some(s => ['pending', 'processing'].includes(s.status));
    if (hasPending) {
      pollRef.current = setInterval(fetchSetDetail, 5000);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [submissions, fetchSetDetail]);

  const handleUploadStudent = async () => {
    if (!studentName.trim()) {
      toast.error('Please enter the student name');
      return;
    }
    if (!answerSheet) {
      toast.error('Please upload an answer sheet');
      return;
    }

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('studentName', studentName.trim());
      formData.append('answerSheet', answerSheet);

      const res = await api.post(`/api/sets/${setId}/submit`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      toast.success(`Uploaded ${studentName.trim()}'s answer sheet`);
      setStudentName('');
      setAnswerSheet(null);

      // Auto-process
      try {
        await api.post(`/api/process/${res.data.submission.id}`);
        toast.success('Processing started...');
      } catch {
        // Will be processed manually
      }

      fetchSetDetail();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const handleProcessSubmission = async (submissionId) => {
    try {
      await api.post(`/api/process/${submissionId}`);
      toast.success('Processing started');
      fetchSetDetail();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to start processing');
    }
  };

  const handleDeleteSet = async () => {
    if (!window.confirm('Delete this set and ALL student submissions? This cannot be undone.')) return;

    try {
      await api.delete(`/api/sets/${setId}`);
      toast.success('Set deleted');
      navigate('/sets');
    } catch (err) {
      toast.error('Failed to delete set');
    }
  };

  // ---- Student Edit/Delete ----
  const handleDeleteSubmission = async (subId, name) => {
    if (!window.confirm(`Delete ${name || 'this student'}'s submission?`)) return;
    try {
      await api.delete(`/api/sets/submission/${subId}`);
      toast.success('Submission deleted');
      fetchSetDetail();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to delete submission');
    }
  };

  const startEdit = (sub) => {
    setEditingId(sub.id);
    setEditName(sub.studentName || '');
    setEditFile(null);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditName('');
    setEditFile(null);
  };

  const handleSaveEdit = async (subId) => {
    if (!editName.trim()) {
      toast.error('Student name cannot be empty');
      return;
    }

    setSaving(true);
    try {
      const formData = new FormData();
      formData.append('studentName', editName.trim());
      if (editFile) {
        formData.append('answerSheet', editFile);
      }

      await api.put(`/api/sets/submission/${subId}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      toast.success('Submission updated');
      cancelEdit();

      // Auto-process if file was re-uploaded
      if (editFile) {
        try {
          await api.post(`/api/process/${subId}`);
          toast.success('Re-processing started...');
        } catch { /* manual */ }
      }

      fetchSetDetail();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to update');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '4rem' }}>
        <div className="loader-ring"><div></div><div></div><div></div><div></div></div>
      </div>
    );
  }

  if (!setData) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">❌</div>
        <h2 className="empty-state-title">Set Not Found</h2>
        <Link to="/sets" className="btn btn-primary">Back to Sets</Link>
      </div>
    );
  }

  return (
    <div>
      {/* Back + Delete */}
      <motion.div
        initial={{ opacity: 0, x: -10 }}
        animate={{ opacity: 1, x: 0 }}
        style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
      >
        <Link to="/sets" className="btn btn-secondary" id="back-to-sets">
          <HiOutlineArrowLeft /> Back to Sets
        </Link>
        <button className="btn btn-danger" onClick={handleDeleteSet} id="delete-set-btn" style={{ fontSize: '0.8rem', padding: '0.5rem 1rem' }}>
          <HiOutlineTrash /> Delete Set
        </button>
      </motion.div>

      {/* Set Header */}
      <motion.div
        className="set-detail-header glass-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <motion.h1
          className="page-title"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          style={{ fontSize: '1.75rem', marginBottom: '0.25rem' }}
        >
          {setData.setName}
        </motion.h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
          Created {new Date(setData.createdAt).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
          {' · '}{setData.questionsCount} questions · {setData.totalMaxMarks} total marks
        </p>

        <div className="set-detail-stats">
          <div className="set-detail-stat">
            <div className="set-detail-stat-value">{stats?.totalStudents || 0}</div>
            <div className="set-detail-stat-label">Students</div>
          </div>
          <div className="set-detail-stat">
            <div className="set-detail-stat-value">{stats?.evaluated || 0}</div>
            <div className="set-detail-stat-label">Evaluated</div>
          </div>
          <div className="set-detail-stat">
            <div className="set-detail-stat-value">{stats?.pending || 0}</div>
            <div className="set-detail-stat-label">Pending</div>
          </div>
          <div className="set-detail-stat">
            <div className={`set-detail-stat-value ${stats?.averageScore > 0 ? getScoreClass(stats.averageScore) : ''}`}>
              {stats?.averageScore > 0 ? `${stats.averageScore}%` : '—'}
            </div>
            <div className="set-detail-stat-label">Average</div>
          </div>
        </div>
      </motion.div>

      {/* Upload Student Answer */}
      <motion.div
        className="student-submit-form glass-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >
        <h2 className="section-title">
          <HiOutlineUserAdd style={{ color: 'var(--primary-light)' }} />
          Add Student Answer
        </h2>

        <div className="student-submit-row">
          <div className="input-group">
            <label className="input-label" htmlFor="student-name">Student Name</label>
            <input
              id="student-name"
              className="input"
              type="text"
              placeholder="Enter student name"
              value={studentName}
              onChange={(e) => setStudentName(e.target.value)}
            />
          </div>

          <div className="input-group">
            <label className="input-label">Answer Sheet</label>
            <FileDropzone
              file={answerSheet}
              onFileSelect={setAnswerSheet}
              accept={{ 'application/pdf': ['.pdf'], 'image/*': ['.jpg', '.jpeg', '.png'] }}
              label="Drop answer sheet"
              hint="PDF, JPG, PNG"
            />
          </div>

          <motion.button
            className="btn btn-primary"
            onClick={handleUploadStudent}
            disabled={!studentName.trim() || !answerSheet || uploading}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            style={{ height: 'fit-content', whiteSpace: 'nowrap' }}
          >
            <HiOutlineLightningBolt />
            {uploading ? 'Uploading...' : 'Upload & Evaluate'}
          </motion.button>
        </div>
      </motion.div>

      {/* Score Distribution Chart */}
      {chartData.length > 0 && (
        <motion.div
          className="chart-container glass-card"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <h2 className="section-title">
            <HiOutlineChartBar style={{ color: 'var(--accent-light)' }} />
            Score Distribution
          </h2>

          <div className="chart-bar-group">
            {chartData
              .sort((a, b) => b.percentage - a.percentage)
              .map((item, i) => (
                <motion.div
                  className="chart-bar-row"
                  key={i}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.3 + i * 0.05 }}
                >
                  <div className="chart-bar-label" title={item.studentName}>
                    {item.studentName}
                  </div>
                  <div className="chart-bar-track">
                    <motion.div
                      className="chart-bar-fill"
                      style={{ background: getBarColor(item.percentage) }}
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.max(item.percentage, 5)}%` }}
                      transition={{ delay: 0.4 + i * 0.05, duration: 0.8, ease: 'easeOut' }}
                    >
                      {item.percentage}%
                    </motion.div>
                  </div>
                  <div className="chart-bar-value">
                    {item.marksAwarded}/{item.totalMaxMarks}
                  </div>
                </motion.div>
              ))}
          </div>
        </motion.div>
      )}

      {/* Students List */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
      >
        <h2 className="section-title" style={{ marginTop: '0.5rem' }}>
          <HiOutlineDocumentText style={{ color: 'var(--primary-light)' }} />
          Student Submissions ({submissions.length})
        </h2>

        {submissions.length === 0 ? (
          <div className="glass-card" style={{ padding: '3rem', textAlign: 'center' }}>
            <p style={{ color: 'var(--text-muted)' }}>No student submissions yet. Upload the first one above!</p>
          </div>
        ) : (
          <div className="students-list">
            <AnimatePresence>
              {submissions.map((sub, i) => (
                <motion.div
                  key={sub.id}
                  className="student-row"
                  initial={{ opacity: 0, x: -15 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 15 }}
                  transition={{ delay: i * 0.04 }}
                  layout
                >
                  <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'var(--gradient-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '0.875rem', color: 'white', flexShrink: 0 }}>
                    {(editingId === sub.id ? editName : sub.studentName)?.charAt(0).toUpperCase() || '?'}
                  </div>

                  {/* Name — editable or static */}
                  {editingId === sub.id ? (
                    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                      <input
                        className="input"
                        type="text"
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        placeholder="Student name"
                        style={{ fontSize: '0.875rem', padding: '0.5rem 0.75rem' }}
                        autoFocus
                      />
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', cursor: 'pointer' }}>
                          <input
                            type="file"
                            accept=".pdf,.jpg,.jpeg,.png"
                            style={{ display: 'none' }}
                            onChange={(e) => setEditFile(e.target.files[0] || null)}
                          />
                          <span className="btn btn-secondary" style={{ padding: '0.25rem 0.5rem', fontSize: '0.7rem' }}>
                            {editFile ? `📎 ${editFile.name.substring(0, 20)}` : '📎 Replace file (optional)'}
                          </span>
                        </label>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="student-row-name">{sub.studentName || 'Unknown'}</div>
                      <div className="student-row-file">{sub.originalFileName}</div>
                    </>
                  )}

                  {/* Status */}
                  {editingId !== sub.id && (
                    <div>
                      <span className={`status-badge ${sub.status}`}>
                        {sub.status === 'completed' && <HiOutlineCheckCircle />}
                        {sub.status === 'processing' && <HiOutlineClock />}
                        {sub.status === 'pending' && <HiOutlineClock />}
                        {sub.status}
                      </span>
                    </div>
                  )}

                  {/* Score */}
                  {editingId !== sub.id && (
                    sub.result ? (
                      <div className={`student-row-score ${getScoreClass(sub.result.percentage)}`}>
                        {sub.result.percentage}%
                      </div>
                    ) : (
                      <div className="student-row-score" style={{ color: 'var(--text-muted)' }}>—</div>
                    )
                  )}

                  {/* Actions */}
                  <div className="student-row-actions">
                    {editingId === sub.id ? (
                      /* Edit mode buttons */
                      <>
                        <button
                          className="btn btn-primary"
                          style={{ padding: '0.375rem 0.75rem', fontSize: '0.75rem' }}
                          onClick={() => handleSaveEdit(sub.id)}
                          disabled={saving}
                        >
                          <HiOutlineCheck /> {saving ? '...' : 'Save'}
                        </button>
                        <button
                          className="btn btn-secondary"
                          style={{ padding: '0.375rem 0.75rem', fontSize: '0.75rem' }}
                          onClick={cancelEdit}
                        >
                          <HiOutlineX />
                        </button>
                      </>
                    ) : (
                      /* Normal mode buttons */
                      <>
                        {sub.result && (
                          <Link
                            to={`/results/${sub.result.resultId}`}
                            className="btn btn-secondary"
                            style={{ padding: '0.375rem 0.75rem', fontSize: '0.75rem' }}
                          >
                            <HiOutlineEye /> View
                          </Link>
                        )}
                        {sub.status === 'pending' && (
                          <button
                            className="btn btn-primary"
                            style={{ padding: '0.375rem 0.75rem', fontSize: '0.75rem' }}
                            onClick={() => handleProcessSubmission(sub.id)}
                          >
                            <HiOutlineLightningBolt /> Process
                          </button>
                        )}
                        {sub.status === 'failed' && (
                          <button
                            className="btn btn-secondary"
                            style={{ padding: '0.375rem 0.75rem', fontSize: '0.75rem' }}
                            onClick={() => handleProcessSubmission(sub.id)}
                            title={sub.errorMessage}
                          >
                            ↻ Retry
                          </button>
                        )}
                        <button
                          className="btn btn-secondary btn-icon"
                          style={{ width: 30, height: 30, fontSize: '0.8rem' }}
                          onClick={() => startEdit(sub)}
                          title="Edit student"
                        >
                          <HiOutlinePencil />
                        </button>
                        <button
                          className="btn btn-secondary btn-icon"
                          style={{ width: 30, height: 30, fontSize: '0.8rem', color: 'var(--error)' }}
                          onClick={() => handleDeleteSubmission(sub.id, sub.studentName)}
                          title="Delete student"
                        >
                          <HiOutlineTrash />
                        </button>
                      </>
                    )}
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </motion.div>
    </div>
  );
}
