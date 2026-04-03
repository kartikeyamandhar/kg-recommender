import { useState, useRef } from 'react'

const TABS = ['Text', 'PDF', 'Image', 'Audio']
const ACCEPT = { PDF: '.pdf', Image: '.jpg,.jpeg,.png,.webp', Audio: '.mp3,.wav,.m4a' }
const ENDPOINTS = { Text: '/ingest/text', PDF: '/ingest/pdf', Image: '/ingest/image', Audio: '/ingest/audio' }
const ICONS = {
  Text: '✎',
  PDF: '⬚',
  Image: '⊡',
  Audio: '◎',
}

export default function UploadZone({ onStream, streaming }) {
  const [tab, setTab] = useState('Text')
  const [text, setText] = useState('')
  const [file, setFile] = useState(null)
  const [dragging, setDragging] = useState(false)
  const fileRef = useRef()

  const handleSubmit = () => {
    if (tab === 'Text') {
      if (!text.trim()) return
      onStream(ENDPOINTS.Text, { text }, false)
    } else {
      if (!file) return
      const fd = new FormData()
      fd.append('file', file)
      onStream(ENDPOINTS[tab], fd, true)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped) setFile(dropped)
  }

  const handleTabChange = (t) => { setTab(t); setFile(null) }
  const canSubmit = !streaming && (tab === 'Text' ? text.trim().length > 0 : file !== null)

  return (
    <div className="flex flex-col gap-3">
      <p className="text-caption font-semibold text-gray-500 uppercase tracking-wider">Upload Content</p>

      {/* Tabs */}
      <div className="grid grid-cols-4 gap-1 bg-surface-base rounded-lg p-1">
        {TABS.map(t => (
          <button
            key={t}
            onClick={() => handleTabChange(t)}
            className={`flex flex-col items-center gap-0.5 py-2 rounded-md text-caption font-medium transition-all
              ${tab === t
                ? 'bg-surface-card text-white shadow-sm'
                : 'text-gray-500 hover:text-gray-300 hover:bg-surface-card/50'
              }`}
          >
            <span className="text-base leading-none">{ICONS[t]}</span>
            <span>{t}</span>
          </button>
        ))}
      </div>

      {/* Input */}
      {tab === 'Text' ? (
        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          placeholder="Paste text, articles, notes, or any content…"
          rows={7}
          className="w-full bg-surface-base border border-surface-border rounded-lg px-3 py-2.5
                     text-body text-gray-200 placeholder-gray-600 resize-none
                     focus:outline-none focus:border-surface-muted transition-colors"
        />
      ) : (
        <div
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
          className={`flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed
                      cursor-pointer transition-all py-8
                      ${dragging
                        ? 'border-accent-primary bg-accent-muted/20'
                        : file
                          ? 'border-surface-muted bg-surface-card'
                          : 'border-surface-border bg-surface-base hover:border-surface-muted hover:bg-surface-card/30'
                      }`}
        >
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPT[tab]}
            className="hidden"
            onChange={e => setFile(e.target.files[0])}
          />
          {file ? (
            <>
              <div className="w-8 h-8 rounded-lg bg-accent-primary/20 flex items-center justify-center text-accent-primary text-lg">
                {ICONS[tab]}
              </div>
              <span className="text-body font-medium text-gray-200">{file.name}</span>
              <span className="text-caption text-gray-500">{(file.size / 1024).toFixed(1)} KB · click to change</span>
            </>
          ) : (
            <>
              <div className="w-8 h-8 rounded-lg bg-surface-card flex items-center justify-center text-gray-500 text-lg">
                {ICONS[tab]}
              </div>
              <span className="text-body text-gray-400">Drop file or click to browse</span>
              <span className="text-caption text-gray-600">{ACCEPT[tab].replace(/\./g, '').toUpperCase()}</span>
            </>
          )}
        </div>
      )}

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={!canSubmit}
        className={`w-full py-2.5 rounded-lg text-label font-semibold transition-all
          ${canSubmit
            ? 'bg-accent-primary hover:bg-accent-hover text-white shadow-lg shadow-accent-primary/20 active:scale-[0.98]'
            : 'bg-surface-card text-gray-600 cursor-not-allowed'
          }`}
      >
        {streaming ? (
          <span className="flex items-center justify-center gap-2">
            <span className="w-3.5 h-3.5 rounded-full border-2 border-gray-600 border-t-white animate-spin" />
            Processing…
          </span>
        ) : (
          <span className="flex items-center justify-center gap-2">
            <span>Extract & Build Graph</span>
          </span>
        )}
      </button>
    </div>
  )
}