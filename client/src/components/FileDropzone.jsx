import { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { motion, AnimatePresence } from 'framer-motion';
import { HiOutlineCloudUpload, HiOutlineDocumentText, HiOutlineX } from 'react-icons/hi';

export default function FileDropzone({ onFileSelect, file, accept, label, hint }) {
  const onDrop = useCallback((acceptedFiles) => {
    if (acceptedFiles.length > 0) {
      onFileSelect(acceptedFiles[0]);
    }
  }, [onFileSelect]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept,
    multiple: false
  });

  const formatSize = (bytes) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  return (
    <div>
      {!file ? (
        <motion.div
          {...getRootProps()}
          className={`dropzone ${isDragActive ? 'active' : ''}`}
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.99 }}
        >
          <input {...getInputProps()} />
          <motion.div
            className="dropzone-icon"
            animate={{ y: isDragActive ? -8 : 0 }}
            transition={{ type: 'spring', stiffness: 300 }}
          >
            <HiOutlineCloudUpload />
          </motion.div>
          <p className="dropzone-text">{label || 'Drop your file here or click to browse'}</p>
          <p className="dropzone-hint">{hint || 'PDF, JPG, PNG supported'}</p>
        </motion.div>
      ) : (
        <AnimatePresence>
          <motion.div
            className="file-preview"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
          >
            <HiOutlineDocumentText className="file-preview-icon" />
            <div>
              <div className="file-preview-name">{file.name}</div>
              <div className="file-preview-size">{formatSize(file.size)}</div>
            </div>
            <button
              className="file-preview-remove"
              onClick={(e) => { e.stopPropagation(); onFileSelect(null); }}
            >
              <HiOutlineX size={18} />
            </button>
          </motion.div>
        </AnimatePresence>
      )}
    </div>
  );
}
