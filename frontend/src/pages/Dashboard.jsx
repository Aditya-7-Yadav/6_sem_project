import React, { useState } from 'react'
import Header from '../components/Header'
import FileUpload from '../components/FileUpload'
import ResultViewer from '../components/ResultViewer'
import { evaluateAnswers } from '../services/api'

const Dashboard = () => {
  const [ocrResult, setOcrResult] = useState(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [error, setError] = useState(null)
  const [modelAnswer, setModelAnswer] = useState('')
  const [evaluationResult, setEvaluationResult] = useState(null)
  const [isEvaluating, setIsEvaluating] = useState(false)
  const [evaluationError, setEvaluationError] = useState(null)

  const resetEvaluationState = () => {
    setEvaluationResult(null)
    setEvaluationError(null)
  }

  const handleUploadSuccess = (result) => {
    setOcrResult(result)
    setIsProcessing(false)
    setError(null)
    resetEvaluationState()
  }

  const handleUploadError = (message) => {
    setError(message)
    setIsProcessing(false)
    setOcrResult(null)
    resetEvaluationState()
  }

  const handleUploadStart = () => {
    setError(null)
    setIsProcessing(true)
    setOcrResult(null)
    resetEvaluationState()
  }

  const handleReset = () => {
    setOcrResult(null)
    setError(null)
    setIsProcessing(false)
    setModelAnswer('')
    resetEvaluationState()
  }

  const handleModelFileChange = (event) => {
    const file = event.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = () => {
      const text = reader.result
      if (typeof text === 'string') {
        setModelAnswer(text)
      }
    }
    reader.onerror = () => {
      setEvaluationError('Unable to read the model answer file.')
    }
    reader.readAsText(file)
  }

  const handleEvaluate = async () => {
    if (!ocrResult || !modelAnswer.trim()) {
      return
    }

    setIsEvaluating(true)
    setEvaluationError(null)
    setEvaluationResult(null)

    try {
      const payload = {
        student_text: ocrResult,
        model_answer: modelAnswer,
      }
      const response = await evaluateAnswers(payload)
      setEvaluationResult(response)
    } catch (err) {
      setEvaluationError(err.message)
    } finally {
      setIsEvaluating(false)
    }
  }

  const evaluationDisabled = !ocrResult || !modelAnswer.trim() || isEvaluating

  return (
    <div className="min-h-screen bg-slate-50">
      <Header />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-slate-900 mb-2">
            Document Processing
          </h1>
          <p className="text-slate-600">
            Upload a PDF to extract the student response, then compare it
            with a model answer.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1.05fr_0.95fr] gap-8">
          <div className="space-y-6">
            <FileUpload
              onUploadSuccess={handleUploadSuccess}
              onUploadError={handleUploadError}
              onUploadStart={handleUploadStart}
              isLoading={isProcessing}
            />

            <div className="card space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-semibold text-slate-900">
                    Model Answer
                  </h2>
                  <p className="text-sm text-slate-500">
                    Paste the reference answer or upload a .txt file to load it.
                  </p>
                </div>
                <label className="btn-secondary flex items-center gap-2 cursor-pointer">
                  Upload .txt
                  <input
                    type="file"
                    accept=".txt"
                    onChange={handleModelFileChange}
                    className="hidden"
                  />
                </label>
              </div>
              <textarea
                value={modelAnswer}
                onChange={(event) => setModelAnswer(event.target.value)}
                rows={8}
                placeholder="Enter the master answer that should be used for evaluation"
                className="w-full resize-none border border-slate-200 rounded-xl p-4 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-900"
              />

              <div className="flex flex-col gap-2">
                <button
                  type="button"
                  onClick={handleEvaluate}
                  className="btn-primary w-full"
                  disabled={evaluationDisabled}
                >
                  {isEvaluating ? 'Evaluating answers…' : 'Evaluate Answers'}
                </button>
                {!ocrResult && (
                  <p className="text-xs text-slate-500">
                    Upload a PDF first so the student text is ready for
                    comparison.
                  </p>
                )}
                {!modelAnswer.trim() && (
                  <p className="text-xs text-slate-500">
                    Provide or upload a model answer to run the evaluation.
                  </p>
                )}
                {evaluationError && (
                  <p className="text-sm text-red-600">{evaluationError}</p>
                )}
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <ResultViewer
              studentText={ocrResult}
              modelAnswer={modelAnswer}
              evaluationResult={evaluationResult}
              isLoading={isProcessing}
              onReset={handleReset}
            />
          </div>
        </div>
      </main>
    </div>
  )
}

export default Dashboard