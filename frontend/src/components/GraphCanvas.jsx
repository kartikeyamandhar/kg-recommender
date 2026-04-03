import { useEffect, useRef, useCallback, useState } from 'react'
import * as d3 from 'd3'

const ENTITY_COLOR = {
  person:       '#818cf8',
  concept:      '#a78bfa',
  place:        '#34d399',
  work:         '#fbbf24',
  organization: '#60a5fa',
  other:        '#9ca3af',
}

const ENTITY_LABEL = {
  person:       'Person',
  concept:      'Concept',
  place:        'Place',
  work:         'Work',
  organization: 'Org',
  other:        'Other',
}

const MIN_R = 7
const MAX_R = 22

export default function GraphCanvas({ graphData, highlightPath, onNodeClick }) {
  const svgRef = useRef()
  const simRef = useRef()
  const tooltipRef = useRef()
  const [tooltip, setTooltip] = useState(null)

  const render = useCallback(() => {
    if (!graphData || !svgRef.current) return
    const { nodes, edges } = graphData
    if (!nodes.length) return

    const el = svgRef.current
    const W = el.clientWidth || 800
    const H = el.clientHeight || 500

    const degMap = {}
    edges.forEach(e => {
      degMap[e.source] = (degMap[e.source] || 0) + 1
      degMap[e.target] = (degMap[e.target] || 0) + 1
    })
    const maxDeg = Math.max(1, ...Object.values(degMap))
    const radius = n => MIN_R + ((degMap[n.id] || 0) / maxDeg) * (MAX_R - MIN_R)

    const pathSet = new Set(highlightPath || [])
    const hasHighlight = highlightPath && highlightPath.length > 0

    d3.select(el).selectAll('*').remove()

    const svg = d3.select(el).attr('width', W).attr('height', H)

    const g = svg.append('g')

    svg.call(
      d3.zoom().scaleExtent([0.15, 5])
        .on('zoom', e => g.attr('transform', e.transform))
    )

    // Arrow marker
    svg.append('defs').append('marker')
      .attr('id', 'arrow')
      .attr('viewBox', '0 -4 8 8')
      .attr('refX', 16)
      .attr('refY', 0)
      .attr('markerWidth', 5)
      .attr('markerHeight', 5)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-4L8,0L0,4')
      .attr('fill', '#4b5563')

    svg.append('defs').append('marker')
      .attr('id', 'arrow-highlight')
      .attr('viewBox', '0 -4 8 8')
      .attr('refX', 16)
      .attr('refY', 0)
      .attr('markerWidth', 5)
      .attr('markerHeight', 5)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-4L8,0L0,4')
      .attr('fill', '#f59e0b')

    const nodeMap = {}
    nodes.forEach(n => { nodeMap[n.id] = { ...n } })

    const linkData = edges.map(e => ({
      ...e,
      source: nodeMap[e.source] || e.source,
      target: nodeMap[e.target] || e.target,
    }))
    const nodeData = nodes.map(n => ({ ...n }))

    const sim = d3.forceSimulation(nodeData)
      .force('link', d3.forceLink(linkData).id(d => d.id).distance(100).strength(0.5))
      .force('charge', d3.forceManyBody().strength(-250))
      .force('center', d3.forceCenter(W / 2, H / 2))
      .force('collision', d3.forceCollide().radius(d => radius(d) + 8))
    simRef.current = sim

    // Edge groups
    const linkGroup = g.append('g')

    const link = linkGroup.selectAll('line')
      .data(linkData)
      .join('line')
      .attr('stroke', d => {
        if (!hasHighlight) return '#2d3748'
        const inPath = pathSet.has(d.source.label) && pathSet.has(d.target.label)
        return inPath ? '#f59e0b' : '#1f2937'
      })
      .attr('stroke-width', d => {
        if (!hasHighlight) return 1.5
        const inPath = pathSet.has(d.source.label) && pathSet.has(d.target.label)
        return inPath ? 2.5 : 1
      })
      .attr('stroke-opacity', d => {
        if (!hasHighlight) return 0.5
        const inPath = pathSet.has(d.source.label) && pathSet.has(d.target.label)
        return inPath ? 1 : 0.1
      })
      .attr('marker-end', d => {
        if (!hasHighlight) return 'url(#arrow)'
        const inPath = pathSet.has(d.source.label) && pathSet.has(d.target.label)
        return inPath ? 'url(#arrow-highlight)' : 'url(#arrow)'
      })

    // Edge label (shown on hover via mouse events)
    link.on('mouseover', function(event, d) {
      setTooltip({ x: event.clientX, y: event.clientY, text: d.relation.replace(/_/g, ' ') })
    }).on('mousemove', function(event) {
      setTooltip(prev => prev ? { ...prev, x: event.clientX, y: event.clientY } : null)
    }).on('mouseout', function() {
      setTooltip(null)
    })

    // Node groups
    const node = g.append('g').selectAll('g')
      .data(nodeData)
      .join('g')
      .attr('cursor', 'pointer')
      .call(
        d3.drag()
          .on('start', (event, d) => {
            if (!event.active) sim.alphaTarget(0.3).restart()
            d.fx = d.x; d.fy = d.y
          })
          .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
          .on('end', (event, d) => {
            if (!event.active) sim.alphaTarget(0)
            d.fx = null; d.fy = null
          })
      )
      .on('click', (_, d) => onNodeClick && onNodeClick(d))
      .on('mouseover', function(event, d) {
        setTooltip({ x: event.clientX, y: event.clientY, text: `${d.label} · ${d.type}` })
        d3.select(this).select('circle').attr('stroke-width', 3)
      })
      .on('mousemove', function(event) {
        setTooltip(prev => prev ? { ...prev, x: event.clientX, y: event.clientY } : null)
      })
      .on('mouseout', function(_, d) {
        setTooltip(null)
        d3.select(this).select('circle').attr('stroke-width', pathSet.has(d.label) ? 2.5 : 1.5)
      })

    // Circle
    node.append('circle')
      .attr('r', d => radius(d))
      .attr('fill', d => ENTITY_COLOR[d.type] || ENTITY_COLOR.other)
      .attr('fill-opacity', d => {
        if (!hasHighlight) return 0.85
        return pathSet.has(d.label) ? 1 : 0.2
      })
      .attr('stroke', d => {
        if (pathSet.has(d.label)) return '#f59e0b'
        return ENTITY_COLOR[d.type] || ENTITY_COLOR.other
      })
      .attr('stroke-opacity', d => {
        if (!hasHighlight) return 0.3
        return pathSet.has(d.label) ? 1 : 0.1
      })
      .attr('stroke-width', d => pathSet.has(d.label) ? 2.5 : 1.5)

    // Label
    node.append('text')
      .text(d => d.label.length > 16 ? d.label.slice(0, 15) + '…' : d.label)
      .attr('x', d => radius(d) + 5)
      .attr('y', 4)
      .attr('font-size', 11)
      .attr('font-family', 'Inter, system-ui, sans-serif')
      .attr('fill', d => {
        if (!hasHighlight) return '#9ca3af'
        return pathSet.has(d.label) ? '#e2e8f0' : '#374151'
      })
      .attr('pointer-events', 'none')

    sim.on('tick', () => {
      link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y)
      node.attr('transform', d => `translate(${d.x},${d.y})`)
    })
  }, [graphData, highlightPath, onNodeClick])

  useEffect(() => {
    render()
    return () => simRef.current?.stop()
  }, [render])

  useEffect(() => {
    const ro = new ResizeObserver(() => render())
    if (svgRef.current) ro.observe(svgRef.current.parentElement)
    return () => ro.disconnect()
  }, [render])

  // Entity types present in graph
  const presentTypes = graphData
    ? [...new Set(graphData.nodes.map(n => n.type))].filter(t => ENTITY_COLOR[t])
    : []

  return (
    <div className="w-full h-full relative">
      {(!graphData || !graphData.nodes.length) && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-surface-card border border-surface-border flex items-center justify-center text-2xl text-gray-600">
            ◈
          </div>
          <div className="text-center">
            <p className="text-label text-gray-500">No graph yet</p>
            <p className="text-caption text-gray-600 mt-1">Upload content to extract entities and relationships</p>
          </div>
        </div>
      )}

      <svg ref={svgRef} className="w-full h-full" />

      {/* Legend */}
      {presentTypes.length > 0 && (
        <div className="absolute bottom-3 left-3 flex flex-wrap gap-1.5 bg-surface-panel/90 backdrop-blur-sm border border-surface-border rounded-lg px-3 py-2">
          {presentTypes.map(type => (
            <div key={type} className="flex items-center gap-1.5">
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: ENTITY_COLOR[type] }}
              />
              <span className="text-caption text-gray-400">{ENTITY_LABEL[type] || type}</span>
            </div>
          ))}
        </div>
      )}

      {/* Tooltip */}
      {tooltip && (
        <div
          className="graph-tooltip"
          style={{ left: tooltip.x + 12, top: tooltip.y - 10 }}
        >
          {tooltip.text}
        </div>
      )}
    </div>
  )
}