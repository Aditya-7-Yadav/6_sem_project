import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import toast from 'react-hot-toast';
import { HiOutlineDocumentText, HiOutlineBookOpen, HiOutlineLightningBolt } from 'react-icons/hi';
import api from '../api';
import FileDropzone from '../components/FileDropzone';
import LoadingSpinner from '../components/LoadingSpinner';

export default function Upload() {
  const navigate = useNavigate();
  const [answerSheet, setAnswerSheet] = useState(null);
  const [modelAnswer, setModelAnswer] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [processingStep, setProcessingStep] = useState(0);
  const pollRef = useRef(null);

  const handleSubmit = async () => {
    if (!answerSheet || !modelAnswer) {
      toast.error('Please upload both answer sheet and model answer files');
      return;
    }

    setProcessing(true);
    setProcessingStep(0);

    try {
      // Step 1: Upload files
      const formData = new FormData();
      formData.append('answerSheet', answerSheet);
      formData.append('modelAnswer', modelAnswer);

      setProcessingStep(0);
      const uploadRes = await api.post('/api/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      const submissionId = uploadRes.data.submission.id;
      toast.success(`Uploaded! ${uploadRes.data.submission.questionsFound} questions found`);

      // Step 2: Start processing
      setProcessingStep(2);
      await api.post(`/api/process/${submissionId}`);

      // Step 3: Poll for status
      setProcessingStep(3);
      let stepCounter = 3;
      const stepInterval = setInterval(() => {
        stepCounter = Math.min(stepCounter + 1, 8);
        setProcessingStep(stepCounter);
      }, 4000);

      pollRef.current = setInterval(async () => {
        try {
          const statusRes = await api.get(`/api/process/${submissionId}/status`);
          const { status, resultId } = statusRes.data;

          if (status === 'completed' && resultId) {
            clearInterval(pollRef.current);
            clearInterval(stepInterval);
            toast.success('Evaluation complete!');
            navigate(`/results/${resultId}`);
          } else if (status === 'failed') {
            clearInterval(pollRef.current);
            clearInterval(stepInterval);
            setProcessing(false);
            toast.error('Evaluation failed: ' + (statusRes.data.error || 'Unknown error'));
          }
        } catch {
          // keep polling
        }
      }, 3000);

    } catch (err) {
      setProcessing(false);
      toast.error(err.response?.data?.error || 'Upload failed');
    }
  };

  if (processing) {
    return <LoadingSpinner step={processingStep} />;
  }

  return (
    <div className="upload-container">
      <div className="page-header">
        <motion.h1
          className="page-title"
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
        >
          New Evaluation
        </motion.h1>
        <motion.p
          className="page-subtitle"
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.1 }}
        >
          Upload student answer sheet and model answers to begin AI evaluation
        </motion.p>
      </div>

      {/* Answer Sheet Upload */}
      <motion.div
        className="upload-section"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
      >
        <h2 className="upload-section-title">
          <HiOutlineDocumentText style={{ color: 'var(--primary-light)' }} />
          Student Answer Sheet
        </h2>
        <FileDropzone
          file={answerSheet}
          onFileSelect={setAnswerSheet}
          accept={{ 'application/pdf': ['.pdf'], 'image/*': ['.jpg', '.jpeg', '.png'] }}
          label="Drop the answer sheet here"
          hint="PDF, JPG, PNG — Max 50MB"
        />
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
          disabled={!answerSheet || !modelAnswer}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          style={{ width: '100%', padding: '1rem', fontSize: '1rem' }}
        >
          <HiOutlineLightningBolt />
          Start AI Evaluation
        </motion.button>
      </motion.div>
    </div>
  );
}
