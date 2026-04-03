import { useEffect, useRef } from 'react'

const AGENT_CONFIG = {
  extraction:     { color: 'text-indigo-400',  bg: 'bg-indigo-950/60',  dot: 'bg-indigo-400',  label: 'extract' },
  graph:          { color: 'text-emerald-400', bg: 'bg-emerald-950/60', dot: 'bg-emerald-400', label: 'graph'   },
  recommendation: { color: 'text-violet-400',  bg: 'bg-violet-950/60',  dot: 'bg-violet-400',  label: 'reco'    },
}

export default function AgentTrace({ steps }) {
  const bottomRef = useRef()

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [steps])

  return (
    <div className="flex flex-col h-full">
      <p className="text-caption font-semibold text-gray-500 uppercase tracking-wider mb-3">
        Agent Trace
      </p>
      <div className="flex-1 overflow-y-auto flex flex-col gap-1.5 min-h-0">
        {steps.length === 0 ? (
          <div className="flex flex-col gap-2 pt-2">
            <p className="text-caption text-gray-600 italic">Waiting for content…</p>
            <div className="flex flex-col gap-1">
              {['extract', 'graph', 'reco'].map((label, i) => (
                <div key={i} className="flex items-center gap-2 opacity-20">
                  <span className="w-1.5 h-1.5 rounded-full bg-gray-600" />
                  <span className="font-mono text-caption text-gray-600">[{label}]</span>
                  <div className="h-px flex-1 bg-gray-700" />
                </div>
              ))}
            </div>
          </div>
        ) : (
          steps.map((step, i) => {
            const cfg = AGENT_CONFIG[step.agent] || { color: 'text-gray-400', bg: 'bg-gray-900', dot: 'bg-gray-400', label: step.agent }
            return (
              <div key={i} className={`flex gap-2 items-start rounded-md px-2 py-1.5 ${cfg.bg}`}>
                <span className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${cfg.dot}`} />
                <div className="flex flex-col gap-0.5 min-w-0">
                  <span className={`font-mono text-caption font-semibold ${cfg.color}`}>
                    [{cfg.label}]
                  </span>
                  <span className="text-caption text-gray-400 leading-relaxed break-words">
                    {step.message}
                  </span>
                </div>
              </div>
            )
          })
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}