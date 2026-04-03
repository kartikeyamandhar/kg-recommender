import { useState, useCallback, useEffect } from 'react'
import { useStream } from './hooks/useStream'
import UploadZone from './components/UploadZone'
import AgentTrace from './components/AgentTrace'
import GraphCanvas from './components/GraphCanvas'
import RecoPanel from './components/RecoPanel'
import ChatPanel from './components/ChatPanel'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

async function fetchGraph() {
  const res = await fetch(`${API_BASE}/graph`)
  if (!res.ok) return null
  return res.json()
}

const RIGHT_TABS = ['Graph', 'Chat']

export default function App() {
  const ingest = useStream()
  const reco   = useStream()

  const [graphData, setGraphData]         = useState(null)
  const [highlightPath, setHighlightPath] = useState([])
  const [activeSteps, setActiveSteps]     = useState([])
  const [rightTab, setRightTab]           = useState('Graph')

  useEffect(() => {
    if (ingest.graphUpdated || ingest.done) {
      fetchGraph().then(data => { if (data) setGraphData(data) })
    }
  }, [ingest.graphUpdated, ingest.done])

  useEffect(() => {
    if (ingest.streaming || ingest.steps.length) setActiveSteps(ingest.steps)
  }, [ingest.steps, ingest.streaming])

  useEffect(() => {
    if (reco.streaming || reco.steps.length) {
      setActiveSteps([...ingest.steps, ...reco.steps])
    }
  }, [reco.steps, reco.streaming, ingest.steps])

  useEffect(() => {
    if (reco.recommendations.length) setHighlightPath(reco.recommendations[0].path)
    else setHighlightPath([])
  }, [reco.recommendations])

  useEffect(() => {
    if (ingest.done && graphData) setRightTab('Graph')
  }, [ingest.done, graphData])

  const handleNodeClick = useCallback((node) => {
    reco.stream('/recommend', { entity_id: node.id, k: 5 }, false)
  }, [reco])

  const handleRecoSelect = useCallback((entityId) => {
    reco.stream('/recommend', { entity_id: entityId, k: 5 }, false)
  }, [reco])

  const handleIngest = useCallback((endpoint, body, isFormData) => {
    reco.reset()
    setHighlightPath([])
    ingest.stream(endpoint, body, isFormData)
  }, [ingest, reco])

  const handleReset = useCallback(async () => {
    await fetch(`${API_BASE}/graph`, { method: 'DELETE' })
    setGraphData(null)
    setHighlightPath([])
    ingest.reset()
    reco.reset()
    setActiveSteps([])
  }, [ingest, reco])

  const hasGraph = graphData && graphData.nodes.length > 0
  const error = ingest.error || reco.error

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-surface-base">

      {/* Header */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-surface-border bg-surface-panel shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-accent-primary flex items-center justify-center text-white text-xs font-bold">
              K
            </div>
            <span className="text-heading font-semibold text-gray-100">KG Recommender</span>
          </div>
          {(ingest.streaming || reco.streaming) && (
            <div className="flex items-center gap-1.5 bg-surface-card border border-surface-border rounded-full px-2.5 py-1">
              <span className="w-1.5 h-1.5 rounded-full bg-accent-primary animate-pulse" />
              <span className="text-caption text-gray-400">Processing</span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleReset}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-caption font-medium
                       text-gray-500 hover:text-red-400 border border-surface-border hover:border-red-900
                       bg-surface-card hover:bg-red-950/30 transition-all"
          >
            ↺ Reset graph
          </button>
          <a
            href="https://github.com/kartikeyamandhar/kg-recommender"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-caption font-medium
                       text-gray-500 hover:text-gray-300 border border-surface-border
                       bg-surface-card hover:bg-surface-hover transition-all"
          >
            GitHub →
          </a>
        </div>
      </header>

      {/* Error banner */}
      {error && (
        <div className="px-6 py-2 bg-red-950/80 border-b border-red-900 text-caption text-red-300 flex items-center gap-2">
          <span>⚠</span> {error}
        </div>
      )}

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left sidebar */}
        <aside className="w-[280px] shrink-0 flex flex-col border-r border-surface-border bg-surface-panel overflow-hidden">
          <div className="p-4 border-b border-surface-border">
            <UploadZone onStream={handleIngest} streaming={ingest.streaming} />
          </div>
          <div className="flex-1 p-4 overflow-hidden min-h-0">
            <AgentTrace steps={activeSteps} />
          </div>
        </aside>

        {/* Right main area */}
        <main className="flex-1 flex flex-col overflow-hidden">

          {/* Tab bar */}
          <div className="flex items-center gap-0 border-b border-surface-border bg-surface-panel shrink-0 px-4">
            {RIGHT_TABS.map(tab => (
              <button
                key={tab}
                onClick={() => setRightTab(tab)}
                className={`flex items-center gap-2 px-4 py-3 text-caption font-semibold border-b-2 transition-all
                  ${rightTab === tab
                    ? 'border-accent-primary text-gray-100'
                    : 'border-transparent text-gray-500 hover:text-gray-300'
                  }`}
              >
                {tab}
                {tab === 'Graph' && hasGraph && (
                  <span className="bg-surface-card border border-surface-border text-gray-500 text-caption rounded-full px-1.5 py-0.5 leading-none">
                    {graphData.nodes.length}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Graph tab */}
          {rightTab === 'Graph' && (
            <div className="flex-1 flex flex-col overflow-hidden">
              <div className="flex-1 overflow-hidden bg-surface-base relative">
                <GraphCanvas
                  graphData={graphData}
                  highlightPath={highlightPath}
                  onNodeClick={handleNodeClick}
                />
              </div>

              {/* Recommendations strip */}
              <div className="h-60 shrink-0 border-t border-surface-border bg-surface-panel flex flex-col overflow-hidden">
                <div className="px-4 py-2.5 border-b border-surface-border shrink-0 flex items-center justify-between">
                  <span className="text-caption font-semibold text-gray-500 uppercase tracking-wider">
                    Recommendations
                  </span>
                  {reco.recommendations.length > 0 && (
                    <span className="text-caption text-gray-600">
                      {reco.recommendations.length} results · click a card to explore
                    </span>
                  )}
                </div>
                <div className="flex-1 px-4 py-3 overflow-y-auto">
                  <RecoPanel
                    recommendations={reco.recommendations}
                    onSelect={handleRecoSelect}
                  />
                </div>
              </div>
            </div>
          )}

          {/* Chat tab */}
          {rightTab === 'Chat' && (
            <div className="flex-1 overflow-hidden bg-surface-base">
              <ChatPanel hasGraph={!!hasGraph} />
            </div>
          )}
        </main>
      </div>
    </div>
  )
}