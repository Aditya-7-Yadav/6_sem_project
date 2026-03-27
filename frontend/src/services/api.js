import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:3000'
const EVALUATION_URL = import.meta.env.VITE_EVAL_URL || 'http://localhost:4004'

export const uploadPDF = async (file, onProgress) => {
  const formData = new FormData()
  formData.append('file', file)

  try {
    const response = await axios.post(`${API_URL}/run`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const percentCompleted = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          )
          onProgress(percentCompleted)
        }
      },
    })

    return response.data
  } catch (error) {
    console.error('Upload error:', error)
    throw new Error(
      error.response?.data?.message || 
      'Failed to process PDF. Please try again.'
    )
  }
}

export const evaluateAnswers = async (payload) => {
  try {
    const response = await axios.post(`${EVALUATION_URL}/evaluate`, payload)
    return response.data
  } catch (error) {
    console.error('Evaluation error:', error)
    throw new Error(
      error.response?.data?.message ||
        'Failed to evaluate answers. Please try again.'
    )
  }
}
