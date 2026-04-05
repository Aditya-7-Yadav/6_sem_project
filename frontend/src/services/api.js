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
    // Map existing payload to backend /grade endpoint
    const gradingPayload = {
      student_answer: payload.student_text,
      model_answer: payload.model_answer,
      keywords: payload.keywords || {},
    }

    const response = await axios.post(`${API_URL}/grade`, gradingPayload)

    const { success, result, error } = response.data || {}

    if (!success || !result) {
      throw new Error(error || 'Grading failed')
    }

    // Adapt backend result shape to existing frontend expectations
    const finalScore = Number(result.final_score || 0)
    const marksAwarded = result.marks_awarded

    const normalizedScore = Math.max(0, Math.min(1, finalScore)) * 100

    return {
      total_score: normalizedScore,
      per_question_scores: [
        {
          question_index: 1,
          score: normalizedScore,
          feedback:
            marksAwarded === 1
              ? 'Answer is strong and closely matches the model answer.'
              : marksAwarded === 0.5
              ? 'Answer is partially correct. Some key ideas are missing.'
              : 'Answer is weak or does not sufficiently match the model answer.',
        },
      ],
      feedback: [
        `Final score: ${(normalizedScore).toFixed(1)} / 100`,
      ],
    }
  } catch (error) {
    console.error('Evaluation error:', error)
    throw new Error(
      error.response?.data?.message ||
        'Failed to evaluate answers. Please try again.'
    )
  }
}
