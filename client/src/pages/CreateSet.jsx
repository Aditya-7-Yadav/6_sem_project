import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import toast from 'react-hot-toast';
import { HiOutlineBookOpen, HiOutlinePlusCircle } from 'react-icons/hi';
import api from '../api';
import FileDropzone from '../components/FileDropzone';

export default function CreateSet() {
  const navigate = useNavigate();
  const [setName, setSetName] = useState('');
  const [modelAnswer, setModelAnswer] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!setName.trim()) {
      toast.error('Please enter a set name');
      return;
    }
    if (!modelAnswer) {
      toast.error('Please upload a model answer file');
      return;
    }

    setLoading(true);

    try {
      const formData = new FormData();
      formData.append('setName', setName.trim());
      formData.append('modelAnswer', modelAnswer);

      const res = await api.post('/api/sets', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      toast.success(`Set created! ${res.data.set.questionsCount} questions found`);
      navigate(`/sets/${res.data.set.id}`);
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to create set');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="upload-container">
      <div className="page-header">
        <motion.h1
          className="page-title"
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
        >
          Create Evaluation Set
        </motion.h1>
        <motion.p
          className="page-subtitle"
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.1 }}
        >
          Define a set with a model answer, then add students to evaluate
        </motion.p>
      </div>

      {/* Set Name */}
      <motion.div
        className="upload-section"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
      >
        <h2 className="upload-section-title">
          <HiOutlinePlusCircle style={{ color: 'var(--primary-light)' }} />
          Set Name
        </h2>
        <div className="input-group">
          <input
            id="set-name"
            className="input"
            type="text"
            placeholder='e.g., "Unit 1 Test", "Midterm Exam", "Assignment 3"'
            value={setName}
            onChange={(e) => setSetName(e.target.value)}
            style={{ fontSize: '1rem', padding: '0.875rem 1rem' }}
          />
        </div>
      </motion.div>

      {/* Model Answer Upload */}
      <motion.div
        className="upload-section"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.25 }}
      >
        <h2 className="upload-section-title">
          <HiOutlineBookOpen style={{ color: 'var(--accent-light)' }} />
          Model Answer Key
        </h2>
        <FileDropzone
          file={modelAnswer}
          onFileSelect={setModelAnswer}
          accept={{ 'text/plain': ['.txt'], 'application/pdf': ['.pdf'] }}
          label="Drop the model answer file here"
          hint="TXT or PDF format"
        />

        <div className="format-guide">
          <div className="format-guide-title">📋 Required Format for Model Answer File</div>
          <pre>{`Q1 [2]
The throw keyword is used to explicitly throw an exception in Java.

Q2 [5]
Object-oriented programming is a paradigm based on objects
containing data and methods. The four pillars are Encapsulation,
Abstraction, Inheritance, and Polymorphism.

Q3 [1]
JVM stands for Java Virtual Machine.`}</pre>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '8px' }}>
            Each question starts with Q&lt;number&gt; [&lt;marks&gt;] followed by the answer text.
            Questions with &lt; 3 marks are graded as short answers, ≥ 3 as long answers.
          </p>
        </div>
      </motion.div>

      {/* Submit Button */}
      <motion.div
        style={{ marginTop: '2rem' }}
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.35 }}
      >
        <motion.button
          className="btn btn-primary btn-lg"
          onClick={handleSubmit}
          disabled={!setName.trim() || !modelAnswer || loading}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          style={{ width: '100%', padding: '1rem', fontSize: '1rem' }}
        >
          <HiOutlinePlusCircle />
          {loading ? 'Creating Set...' : 'Create Evaluation Set'}
        </motion.button>
      </motion.div>
    </div>
  );
}
