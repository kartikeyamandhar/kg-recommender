import { useState, useRef, useCallback } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

export function useStream() {
  const [steps, setSteps] = useState([])
  const [triples, setTriples] = useState([])
  const [recommendations, setRecommendations] = useState([])
  const [graphUpdated, setGraphUpdated] = useState(null)
  const [done, setDone] = useState(false)
  const [error, setError] = useState(null)
  const [streaming, setStreaming] = useState(false)
  const abortRef = useRef(null)

  const reset = useCallback(() => {
    setSteps([])
    setTriples([])
    setRecommendations([])
    setGraphUpdated(null)
    setDone(false)
    setError(null)
  }, [])

  const stream = useCallback(async (endpoint, body, isFormData = false) => {
    if (abortRef.current) abortRef.current.abort()
    abortRef.current = new AbortController()
    reset()
    setStreaming(true)

    try {
      const headers = isFormData ? {} : { 'Content-Type': 'application/json' }
      const fetchBody = isFormData ? body : JSON.stringify(body)

      const response = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers,
        body: fetchBody,
        signal: abortRef.current.signal,
      })

      if (!response.ok) {
        const text = await response.text()
        setError(`HTTP ${response.status}: ${text}`)
        setStreaming(false)
        return
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done: readerDone, value } = await reader.read()
        if (readerDone) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed.startsWith('data:')) continue
          const payload = trimmed.slice(5).trim()
          if (!payload) continue
          try {
            const event = JSON.parse(payload)
            if (event.type === 'step')               setSteps(p => [...p, event.step])
            else if (event.type === 'triples')       setTriples(event.triples)
            else if (event.type === 'graph_updated') setGraphUpdated(event)
            else if (event.type === 'recommendations') setRecommendations(event.results)
            else if (event.type === 'done')          setDone(true)
            else if (event.type === 'error')         setError(event.message)
          } catch (_) {}
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message)
    } finally {
      setStreaming(false)
    }
  }, [reset])

  return { steps, triples, recommendations, graphUpdated, done, error, streaming, stream, reset }
}