const express = require('express')
const cors = require('cors')

const app = express()
const PORT = process.env.PORT || 4004

app.use(cors())
app.use(express.json({ limit: '10mb' }))
app.use(express.urlencoded({ limit: '10mb', extended: true }))

// Gracefully surface payload-too-large errors
app.use((err, req, res, next) => {
  if (err && err.type === 'entity.too.large') {
    return res.status(413).json({
      message: 'Payload exceeded the limit. Please trim the text before evaluation.',
    })
  }
  return next(err)
})

const tokenize = (text) => text.toLowerCase().match(/\b[a-z0-9]+\b/g) || []

const parseShortAnswers = (text) => {
  if (!text) return []

  const lines = text.replace(/\r/g, '\n').split('\n')
  const answers = []
  let buffer = ''

  lines.forEach((line) => {
    const trimmed = line.trim()
    if (!trimmed) {
      if (buffer) {
        answers.push(buffer.trim())
        buffer = ''
      }
      return
    }

    if (/^\d+[.)]/.test(trimmed) || /^[a-zA-Z]\)/.test(trimmed)) {
      if (buffer) {
        answers.push(buffer.trim())
      }
      buffer = trimmed.replace(/^\d+[.)]\s*/g, '').trim()
      return
    }

    buffer = buffer ? `${buffer} ${trimmed}` : trimmed
  })

  if (buffer) {
    answers.push(buffer.trim())
  }

  if (!answers.length && text.trim()) {
    answers.push(text.trim())
  }

  return answers.filter(Boolean)
}

const scoreAnswer = (studentAnswer, modelAnswer) => {
  const student = studentAnswer.trim()
  const model = modelAnswer.trim()

  if (!model && !student) {
    return 1
  }

  const studentTokens = new Set(tokenize(student))
  const modelTokens = tokenize(model)

  if (!modelTokens.length) {
    return studentTokens.size ? 0.3 : 1
  }

  const uniqueModelTokens = [...new Set(modelTokens)]
  const matches = uniqueModelTokens.filter((token) => studentTokens.has(token)).length
  const coverage = matches / Math.max(uniqueModelTokens.length, 1)
  const lengthRatio =
    Math.min(studentTokens.size, uniqueModelTokens.length) /
    Math.max(studentTokens.size, uniqueModelTokens.length, 1)

  const rawScore = coverage * 0.7 + lengthRatio * 0.3
  return Math.min(1, Math.max(0, rawScore))
}

const craftFeedback = (score) => {
  if (score >= 0.85) {
    return 'Excellent coverage of the reference answer.'
  }
  if (score >= 0.6) {
    return 'Good attempt; include one or two more keywords.'
  }
  if (score >= 0.35) {
    return 'Partial match; expand on the key ideas.'
  }
  return 'Missing important points; revisit the model answer.'
}

app.post('/evaluate', (req, res) => {
  const { student_text = '', model_answer = '' } = req.body || {}

  if (!model_answer.trim()) {
    return res.status(400).json({ message: 'Model answer is required.' })
  }

  const studentSegments = parseShortAnswers(student_text)
  const modelSegments = parseShortAnswers(model_answer)

  const normalizedStudentSegments =
    studentSegments.length > 0 ? studentSegments : ['']

  const normalizedModelSegments =
    modelSegments.length > 0 ? modelSegments : [model_answer.trim()]

  const perQuestionScores = normalizedStudentSegments.map((segment, idx) => {
    const reference = normalizedModelSegments[idx] || normalizedModelSegments[0] || ''
    const similarity = scoreAnswer(segment, reference)
    const percentScore = Number((similarity * 100).toFixed(1))

    return {
      question_index: idx + 1,
      student_answer: segment,
      model_reference: reference,
      score: percentScore,
      feedback: craftFeedback(similarity),
    }
  })

  const totalScore = perQuestionScores.length
    ? Number(
        (
          perQuestionScores.reduce((sum, item) => sum + item.score, 0) /
          perQuestionScores.length
        ).toFixed(1)
      )
    : 0

  const feedback = perQuestionScores.map((item) => item.feedback)

  res.json({
    total_score: totalScore,
    per_question_scores: perQuestionScores,
    feedback,
  })
})

app.listen(PORT, () => {
  console.log(`Short answer evaluator listening on port ${PORT}`)
})
