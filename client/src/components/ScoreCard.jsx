import { motion } from 'framer-motion';

export default function ScoreCard({ icon, value, label, color }) {
  return (
    <motion.div
      className="stat-card glass-card"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -4, boxShadow: '0 12px 40px rgba(0,0,0,0.3)' }}
      transition={{ duration: 0.3 }}
    >
      <div className={`stat-card-icon ${color}`}>{icon}</div>
      <motion.div
        className="stat-card-value"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.2 }}
      >
        {value}
      </motion.div>
      <div className="stat-card-label">{label}</div>
    </motion.div>
  );
}
