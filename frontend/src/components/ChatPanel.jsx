import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

const SUGGESTIONS = [
  "What are the key themes in this content?",
  "Recommend similar items based on what you see",
  "What connections do you notice in the graph?",
  "What should I explore next?",
]

function MarkdownContent({ content }) {
  return (
    <ReactMarkdown
      components={{
        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
        strong: ({ children }) => <strong className="font-semibold text-gray-100">{children}</strong>,
        em: ({ children }) => <em className="italic text-gray-300">{children}</em>,
        ul: ({ children }) => <ul className="list-disc pl-4 mb-2 flex flex-col gap-0.5">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal pl-4 mb-2 flex flex-col gap-0.5">{children}</ol>,
        li: ({ children }) => <li className="text-gray-300">{children}</li>,
        h1: ({ children }) => <h1 className="text-label font-semibold text-gray-100 mb-1 mt-2">{children}</h1>,
        h2: ({ children }) => <h2 className="text-label font-semibold text-gray-100 mb-1 mt-2">{children}</h2>,
        h3: ({ children }) => <h3 className="text-body font-semibold text-gray-200 mb-1 mt-1">{children}</h3>,
        code: ({ children }) => (
          <code className="font-mono text-caption bg-surface-base text-indigo-300 px-1 py-0.5 rounded">
            {children}
          </code>
        ),
        blockquote: ({ children }) => (
          <blockquote className="border-l-2 border-surface-muted pl-3 text-gray-400 italic my-1">
            {children}
          </blockquote>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  )
}

function Message({ role, content, streaming }) {
  return (
    <div className={`flex flex-col gap-1 ${role === 'user' ? 'items-end' : 'items-start'}`}>
      <span className="text-caption text-gray-600 px-1">
        {role === 'user' ? 'You' : 'Assistant'}
      </span>
      <div
        className={`max-w-[85%] rounded-xl px-3.5 py-2.5 text-body leading-relaxed
          ${role === 'user'
            ? 'bg-accent-primary text-white rounded-tr-sm whitespace-pre-wrap'
            : 'bg-surface-card text-gray-300 border border-surface-border rounded-tl-sm'
          }`}
      >
        {role === 'assistant'
          ? <MarkdownContent content={content} />
          : content
        }
        {streaming && (
          <span className="inline-block w-1.5 h-3.5 bg-gray-400 ml-0.5 animate-pulse rounded-sm align-middle" />
        )}
      </div>
    </div>
  )
}

export default function ChatPanel({ hasGraph }) {
  const [history, setHistory] = useState([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const bottomRef = useRef()
  const textareaRef = useRef()
  const abortRef = useRef()

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history, streamingText])

  const send = useCallback(async (message) => {
    if (!message.trim() || streaming) return

    const userMessage = message.trim()
    setInput('')
    setStreaming(true)
    setStreamingText('')

    if (textareaRef.current) textareaRef.current.style.height = '36px'

    const newHistory = [...history, { role: 'user', content: userMessage }]
    setHistory(newHistory)

    if (abortRef.current) abortRef.current.abort()
    abortRef.current = new AbortController()

    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage, history }),
        signal: abortRef.current.signal,
      })

      if (!response.ok) {
        setHistory(h => [...h, { role: 'assistant', content: 'Error: could not reach server.' }])
        setStreaming(false)
        return
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let fullText = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
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
            if (event.type === 'chunk') {
              fullText += event.text
              setStreamingText(fullText)
            } else if (event.type === 'done') {
              setHistory(h => [...h, { role: 'assistant', content: fullText }])
              setStreamingText('')
              setStreaming(false)
            } else if (event.type === 'error') {
              setHistory(h => [...h, { role: 'assistant', content: `Error: ${event.message}` }])
              setStreamingText('')
              setStreaming(false)
            }
          } catch (_) {}
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setHistory(h => [...h, { role: 'assistant', content: 'Connection error.' }])
      }
      setStreamingText('')
      setStreaming(false)
    }
  }, [history, streaming])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send(input)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-4 min-h-0">
        {history.length === 0 && !streaming ? (
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-1">
              <p className="text-label font-medium text-gray-300">
                {hasGraph ? 'Ask about your content' : 'Upload content to start'}
              </p>
              <p className="text-caption text-gray-500">
                {hasGraph
                  ? 'The assistant has full context from your knowledge graph.'
                  : 'Upload text, PDF, image, or audio first.'}
              </p>
            </div>
            {hasGraph && (
              <div className="grid grid-cols-1 gap-2">
                {SUGGESTIONS.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => send(s)}
                    className="text-left text-caption text-gray-400 bg-surface-card hover:bg-surface-hover
                               border border-surface-border hover:border-surface-muted rounded-lg px-3 py-2.5
                               transition-all active:scale-[0.98]"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <>
            {history.map((msg, i) => (
              <Message key={i} role={msg.role} content={msg.content} streaming={false} />
            ))}
            {streaming && streamingText && (
              <Message role="assistant" content={streamingText} streaming={true} />
            )}
            {streaming && !streamingText && (
              <div className="flex items-start">
                <div className="bg-surface-card border border-surface-border rounded-xl rounded-tl-sm px-3.5 py-2.5">
                  <span className="flex gap-1 items-center">
                    {[0, 150, 300].map((delay, i) => (
                      <span key={i} className="w-1.5 h-1.5 rounded-full bg-gray-500 animate-bounce"
                        style={{ animationDelay: `${delay}ms` }} />
                    ))}
                  </span>
                </div>
              </div>
            )}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="px-4 pb-4 pt-2 border-t border-surface-border shrink-0">
        <div className="flex gap-2 items-end bg-surface-card border border-surface-border rounded-xl px-3 py-2
                        focus-within:border-surface-muted transition-colors">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={hasGraph ? 'Ask anything about the content…' : 'Upload content first…'}
            disabled={!hasGraph || streaming}
            rows={1}
            className="flex-1 bg-transparent text-body text-gray-200 placeholder-gray-600 resize-none
                       focus:outline-none disabled:opacity-40 disabled:cursor-not-allowed py-0.5"
            style={{ minHeight: '24px', maxHeight: '120px' }}
            onInput={e => {
              e.target.style.height = 'auto'
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
            }}
          />
          <button
            onClick={() => send(input)}
            disabled={!hasGraph || streaming || !input.trim()}
            className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 transition-all
              bg-accent-primary hover:bg-accent-hover text-white
              disabled:bg-surface-muted disabled:text-gray-600 disabled:cursor-not-allowed active:scale-95"
          >
            {streaming
              ? <span className="w-3 h-3 rounded-full border-2 border-gray-500 border-t-white animate-spin" />
              : <span className="text-sm leading-none">↑</span>
            }
          </button>
        </div>
        <p className="text-caption text-gray-700 mt-1.5 pl-1">Enter to send · Shift+Enter for newline</p>
      </div>
    </div>
  )
}