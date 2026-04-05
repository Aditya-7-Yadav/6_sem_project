import { motion } from 'framer-motion';

const steps = [
  'Uploading files...',
  'Converting to PDF...',
  'Running OCR extraction...',
  'Parsing student answers...',
  'Classifying question types...',
  'Evaluating short answers...',
  'Evaluating long answers...',
  'Aggregating scores...',
  'Generating report...'
];

export default function LoadingSpinner({ step = 0, message }) {
  const currentStep = message || steps[Math.min(step, steps.length - 1)];

  return (
    <div className="processing-overlay">
      <motion.div
        className="processing-spinner"
        animate={{ rotate: 360 }}
        transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
      />
      <motion.p
        className="processing-text"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
      >
        Processing Evaluation
      </motion.p>
      <motion.p
        className="processing-step"
        key={currentStep}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
      >
        {currentStep}
      </motion.p>

      <div style={{ display: 'flex', gap: '6px', marginTop: '8px' }}>
        {steps.map((_, i) => (
          <motion.div
            key={i}
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: i <= step ? 'var(--primary)' : 'rgba(255,255,255,0.1)'
            }}
            animate={i === step ? { scale: [1, 1.3, 1] } : {}}
            transition={{ duration: 0.8, repeat: Infinity }}
          />
        ))}
      </div>
    </div>
  );
}
