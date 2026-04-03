const SCORE_BAR_COLOR = (score) => {
  if (score >= 0.6) return 'bg-emerald-500'
  if (score >= 0.35) return 'bg-amber-500'
  return 'bg-gray-500'
}

const SCORE_TEXT_COLOR = (score) => {
  if (score >= 0.6) return 'text-emerald-400'
  if (score >= 0.35) return 'text-amber-400'
  return 'text-gray-400'
}

export default function RecoPanel({ recommendations, onSelect }) {
  if (!recommendations.length) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-2 py-4">
        <div className="w-8 h-8 rounded-full bg-surface-card flex items-center justify-center text-gray-600 text-lg">
          ◈
        </div>
        <p className="text-caption text-gray-600 text-center">
          Click any node in the graph<br />to get recommendations
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2 h-full">
      <div className="flex flex-col gap-2 overflow-y-auto">
        {recommendations.map((rec, i) => (
          <div
            key={rec.entity_id}
            onClick={() => onSelect(rec.entity_id)}
            className="group flex flex-col gap-2 p-3 rounded-lg bg-surface-card border border-surface-border
                       hover:border-surface-muted hover:bg-surface-hover cursor-pointer transition-all"
          >
            {/* Top row */}
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-caption font-mono text-gray-600 shrink-0">#{i + 1}</span>
                <span className="text-label font-semibold text-gray-100 truncate">{rec.label}</span>
              </div>
              <span className={`text-caption font-semibold tabular-nums shrink-0 ${SCORE_TEXT_COLOR(rec.score)}`}>
                {(rec.score * 100).toFixed(0)}%
              </span>
            </div>

            {/* Score bar */}
            <div className="h-0.5 bg-surface-base rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${SCORE_BAR_COLOR(rec.score)}`}
                style={{ width: `${Math.min(rec.score * 100, 100)}%` }}
              />
            </div>

            {/* Path */}
            <div className="flex flex-wrap gap-1 items-center">
              {rec.path.map((node, j) => (
                <span key={j} className="flex items-center gap-1">
                  <span className="text-caption text-gray-400 bg-surface-base px-1.5 py-0.5 rounded border border-surface-border">
                    {node}
                  </span>
                  {j < rec.path.length - 1 && (
                    <span className="text-caption text-gray-600">→</span>
                  )}
                </span>
              ))}
            </div>

            {/* Explanation */}
            <p className="text-caption text-gray-500 leading-relaxed">{rec.explanation}</p>
          </div>
        ))}
      </div>
    </div>
  )
}