import React, { useState } from 'react'

const ResultViewer = ({
  studentText,
  modelAnswer,
  evaluationResult,
  isLoading,
  onReset,
}) => {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    if (!studentText) return
    try {
      await navigator.clipboard.writeText(studentText)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy text:', err)
    }
  }

  const wordCount = studentText
    ? studentText.split(/\s+/).filter(Boolean).length
    : 0

  if (isLoading) {
    return (
      <div className="card h-[600px] flex flex-col items-center justify-center">
        <div className="text-center space-y-4">
          <div className="w-16 h-16 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto">
            <svg className="animate-spin h-8 w-8 text-slate-600" fill="none" viewBox="0 0 24 24">
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
          </div>
          <div>
            <h3 className="text-lg font-semibold text-slate-900 mb-1">
              Processing Document
            </h3>
            <p className="text-sm text-slate-600">
              Extracting text from your PDF…
            </p>
          </div>
        </div>
      </div>
    )
  }

  if (!studentText) {
    return (
      <div className="card h-[600px] flex flex-col items-center justify-center">
        <div className="text-center space-y-4 max-w-sm">
          <div className="w-16 h-16 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto">
            <svg
              className="w-8 h-8 text-slate-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
          </div>
          <div>
            <h3 className="text-lg font-semibold text-slate-900 mb-2">
              Waiting for OCR
            </h3>
            <p className="text-sm text-slate-600">
              Upload a PDF document to see the extracted student response here.
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="card space-y-4">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-xl font-semibold text-slate-900">
              Extracted Student Text
            </h2>
            <p className="text-sm text-slate-500">
              The OCR output that will be compared against the model answer.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="flex items-center space-x-2 px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors text-sm font-medium"
            >
              {copied ? (
                <span>Copied!</span>
              ) : (
                <>
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                    />
                  </svg>
                  <span>Copy</span>
                </>
              )}
            </button>
            <button
              onClick={onReset}
              className="text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg p-2 transition-colors"
              title="Clear result"
            >
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>
        </div>

        <div
          className="bg-slate-50 rounded-lg p-6 border border-slate-200 max-h-[340px] overflow-y-auto"
        >
          <pre className="font-mono text-sm text-slate-800 whitespace-pre-wrap break-words">
            {studentText}
          </pre>
        </div>

        <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
          <span>{studentText.length} characters</span>
          <span>{wordCount} words</span>
        </div>
      </div>

      <div className="card space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold text-slate-900">
              Model Answer Preview
            </h2>
            <p className="text-sm text-slate-500">
              What you entered in the model answer card.
            </p>
          </div>
          {modelAnswer && (
            <span className="text-xs font-semibold text-slate-500">Ready</span>
          )}
        </div>
        <div className="bg-slate-50 rounded-lg p-4 border border-slate-200 min-h-[160px]">
          {modelAnswer ? (
            <pre className="font-mono text-sm text-slate-800 whitespace-pre-wrap break-words">
              {modelAnswer}
            </pre>
          ) : (
            <p className="text-sm text-slate-500">
              Enter or upload the perfect answer to compare it against the
              student response.
            </p>
          )}
        </div>
      </div>

      {evaluationResult && (
        <div className="card space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold text-slate-900">
                Evaluation Summary
              </h2>
              <p className="text-sm text-slate-500">
                Scores are normalized out of 100.
              </p>
            </div>
            <p className="text-3xl font-bold text-slate-900">
              {Number(evaluationResult.total_score ?? 0).toFixed(1)}
              <span className="text-sm text-slate-500"> / 100</span>
            </p>
          </div>

          <div className="grid gap-3">
            {evaluationResult.per_question_scores?.map((item) => (
              <div
                key={item.question_index}
                className="border border-slate-200 rounded-2xl p-4 bg-white"
              >
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-slate-900">
                    Question {item.question_index}
                  </p>
                  <p className="text-sm font-semibold text-slate-900">
                    {item.score.toFixed(1)}%
                  </p>
                </div>
                {item.feedback && (
                  <p className="text-xs text-slate-500 mt-2">
                    {item.feedback}
                  </p>
                )}
              </div>
            ))}
          </div>

          {evaluationResult.feedback?.length > 0 && (
            <div className="bg-slate-50 rounded-2xl p-4 border border-slate-200 text-sm text-slate-600">
              <p className="font-semibold text-slate-800 mb-2">Feedback</p>
              <ul className="list-disc pl-4 space-y-1">
                {evaluationResult.feedback.map((note, index) => (
                  <li key={index}>{note}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default ResultViewer