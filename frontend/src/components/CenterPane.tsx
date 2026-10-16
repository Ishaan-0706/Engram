'use client';

import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { GraphLink, GraphNode, EntityLabel } from '@/types';
import { 
  Maximize2, 
  ZoomIn, 
  ZoomOut, 
  RotateCcw, 
  Layers, 
  Info, 
  Sparkles,
  Search,
  Filter,
  Eye,
  X
} from 'lucide-react';

// Dynamic import with SSR disabled since react-force-graph-2d requires browser window & canvas
const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { 
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex flex-col items-center justify-center bg-slate-950 text-slate-400 gap-3">
      <div className="w-8 h-8 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
      <span className="text-xs font-mono">Initializing 2D Force Graph Engine...</span>
    </div>
  )
});

interface CenterPaneProps {
  nodes: GraphNode[];
  links: GraphLink[];
  highlightedEvidenceId: string | null;
  onNodeClick?: (node: GraphNode) => void;
}

export const CenterPane: React.FC<CenterPaneProps> = ({
  nodes,
  links,
  highlightedEvidenceId,
  onNodeClick,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  // Resize observer to fill flex-1 container dynamically
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        setDimensions({
          width: Math.floor(entry.contentRect.width),
          height: Math.floor(entry.contentRect.height),
        });
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  // Compute active highlight path: System -> Decision -> Evidence
  const highlightSet = useMemo(() => {
    const nodeIds = new Set<string>();
    const linkKeys = new Set<string>();

    if (highlightedEvidenceId) {
      // Find the evidence node
      nodeIds.add(highlightedEvidenceId);

      // Find decisions connected to this evidence via SUPPORTED_BY
      const connectedDecisions: string[] = [];
      links.forEach((l) => {
        const s = typeof l.source === 'object' ? (l.source as any).id : l.source;
        const t = typeof l.target === 'object' ? (l.target as any).id : l.target;
        if (t === highlightedEvidenceId || s === highlightedEvidenceId) {
          const other = t === highlightedEvidenceId ? s : t;
          nodeIds.add(other);
          linkKeys.add(`${s}->${t}`);
          linkKeys.add(`${t}->${s}`);
          connectedDecisions.push(other);
        }
      });

      // Find Systems connected to those decisions via AFFECTS
      links.forEach((l) => {
        const s = typeof l.source === 'object' ? (l.source as any).id : l.source;
        const t = typeof l.target === 'object' ? (l.target as any).id : l.target;
        if (connectedDecisions.includes(s) || connectedDecisions.includes(t)) {
          nodeIds.add(s);
          nodeIds.add(t);
          linkKeys.add(`${s}->${t}`);
          linkKeys.add(`${t}->${s}`);
        }
      });
    }

    return { nodeIds, linkKeys, isHoverActive: !!highlightedEvidenceId };
  }, [highlightedEvidenceId, links]);

  // Handle Canvas Drawing for Node:
  // Node colors: Person (blue), System (emerald), Decision (violet), Document (amber), Evidence (yellow)
  const drawNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const isHighlighted = highlightSet.isHoverActive && highlightSet.nodeIds.has(node.id);
      const isDimmed = highlightSet.isHoverActive && !highlightSet.nodeIds.has(node.id);

      ctx.save();
      ctx.globalAlpha = isDimmed ? 0.15 : 1.0;

      const radius = isHighlighted ? 12 : (node.val ? Math.max(7, node.val / 2) : 8);

      // Draw outer glowing halo if highlighted
      if (isHighlighted) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius + 6, 0, 2 * Math.PI, false);
        ctx.fillStyle = `${node.color}33`; // 20% alpha
        ctx.fill();

        ctx.beginPath();
        ctx.arc(node.x, node.y, radius + 3, 0, 2 * Math.PI, false);
        ctx.fillStyle = `${node.color}66`; // 40% alpha
        ctx.fill();
      }

      // Main Circle
      ctx.beginPath();
      ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
      ctx.fillStyle = node.color || '#3b82f6';
      ctx.fill();

      // Border ring
      ctx.lineWidth = isHighlighted ? 2.5 : 1.5;
      ctx.strokeStyle = isHighlighted ? '#ffffff' : '#0f172a';
      ctx.stroke();

      // Label below node
      if (globalScale >= 0.8 || isHighlighted) {
        const label = node.name || node.id;
        ctx.font = `${isHighlighted ? 'bold ' : ''}${Math.max(9, 11 / globalScale)}px ui-sans-serif, system-ui, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';

        // Background box for label readability
        const textWidth = ctx.measureText(label).width;
        ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
        ctx.fillRect(
          node.x - textWidth / 2 - 3,
          node.y + radius + 3,
          textWidth + 6,
          Math.max(10, 13 / globalScale)
        );

        ctx.fillStyle = isHighlighted ? '#ffffff' : '#cbd5e1';
        ctx.fillText(label, node.x, node.y + radius + 4);
      }

      ctx.restore();
    },
    [highlightSet]
  );

  // Link styling:
  // [:SUPERSEDES] (dashed red line #ef4444)
  // [:SUPPORTED_BY] (solid gold line #eab308)
  const drawLink = useCallback(
    (link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const sId = typeof link.source === 'object' ? link.source.id : link.source;
      const tId = typeof link.target === 'object' ? link.target.id : link.target;
      const linkKey = `${sId}->${tId}`;

      const isPathLink = highlightSet.isHoverActive && highlightSet.linkKeys.has(linkKey);
      const isDimmed = highlightSet.isHoverActive && !isPathLink;

      ctx.save();
      ctx.globalAlpha = isDimmed ? 0.08 : (isPathLink ? 1.0 : 0.6);

      ctx.beginPath();
      ctx.moveTo(link.source.x, link.source.y);
      ctx.lineTo(link.target.x, link.target.y);

      // Dash pattern for [:SUPERSEDES]
      if (link.type === 'SUPERSEDES' || link.dashed) {
        ctx.setLineDash([5, 4]);
        ctx.strokeStyle = '#ef4444'; // red
        ctx.lineWidth = isPathLink ? 3.5 : 2;
      } else if (link.type === 'SUPPORTED_BY') {
        ctx.setLineDash([]);
        ctx.strokeStyle = '#eab308'; // solid gold
        ctx.lineWidth = isPathLink ? 3.5 : 2;
      } else {
        ctx.setLineDash([]);
        ctx.strokeStyle = isPathLink ? '#60a5fa' : (link.color || '#475569');
        ctx.lineWidth = isPathLink ? 2.5 : 1.2;
      }

      ctx.stroke();

      // Draw link label if zoomed in or path is highlighted
      if (globalScale > 1.2 || isPathLink) {
        const midX = (link.source.x + link.target.x) / 2;
        const midY = (link.source.y + link.target.y) / 2;
        ctx.font = `italic ${Math.max(8, 9 / globalScale)}px monospace`;
        ctx.fillStyle = isPathLink ? '#ffffff' : '#94a3b8';
        ctx.fillText(`[:${link.type || link.label}]`, midX, midY - 3);
      }

      ctx.restore();
    },
    [highlightSet]
  );

  return (
    <main className="flex-1 h-[calc(100vh-3.5rem)] bg-slate-950 flex flex-col relative overflow-hidden select-none">
      {/* Pane Top Toolbar */}
      <div className="absolute top-3 left-4 z-10 flex items-center gap-2 bg-slate-900/85 backdrop-blur-md border border-slate-800 rounded-lg p-1.5 shadow-lg">
        <span className="text-[11px] font-mono text-slate-400 px-2 flex items-center gap-1.5 border-r border-slate-800">
          <Layers className="w-3.5 h-3.5 text-indigo-400" />
          FalkorDB Subgraph
        </span>
        <button
          onClick={() => fgRef.current?.zoom(fgRef.current.zoom() * 1.3, 400)}
          title="Zoom In"
          aria-label="Zoom In"
          className="p-1.5 rounded hover:bg-slate-800 text-slate-300 hover:text-white transition-colors"
        >
          <ZoomIn className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => fgRef.current?.zoom(fgRef.current.zoom() / 1.3, 400)}
          title="Zoom Out"
          aria-label="Zoom Out"
          className="p-1.5 rounded hover:bg-slate-800 text-slate-300 hover:text-white transition-colors"
        >
          <ZoomOut className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => fgRef.current?.zoomToFit(400, 40)}
          title="Fit Graph to View"
          aria-label="Fit Graph to View"
          className="p-1.5 rounded hover:bg-slate-800 text-slate-300 hover:text-white transition-colors"
        >
          <Maximize2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Hover Path Indicator Alert */}
      {highlightSet.isHoverActive && (
        <div className="absolute top-3 right-4 z-10 bg-indigo-950/80 border border-indigo-500/40 backdrop-blur-md rounded-lg px-3 py-1.5 text-xs text-indigo-200 flex items-center gap-2 shadow-xl animate-in fade-in duration-200">
          <Sparkles className="w-4 h-4 text-amber-400 animate-spin" />
          <span className="font-mono text-[11px]">
            Path Highlighted: <span className="text-emerald-400">System</span> → <span className="text-violet-400">Decision</span> → <span className="text-yellow-400">Evidence</span>
          </span>
        </div>
      )}

      {/* Canvas container */}
      <div ref={containerRef} className="flex-1 w-full h-full cursor-grab active:cursor-grabbing">
        {dimensions.width > 0 && dimensions.height > 0 && (
          <ForceGraph2D
            ref={fgRef}
            width={dimensions.width}
            height={dimensions.height}
            graphData={{ nodes, links }}
            nodeCanvasObject={drawNode}
            linkCanvasObject={drawLink}
            backgroundColor="#020617" // slate-950
            d3VelocityDecay={0.3}
            cooldownTicks={120}
            onNodeClick={(node: any) => {
              setSelectedNode(node);
              if (onNodeClick) onNodeClick(node);
            }}
          />
        )}
      </div>

      {/* Selected Node Details Card Overlay */}
      {selectedNode && (
        <div className="absolute bottom-16 right-4 z-20 w-80 bg-slate-900/95 border border-slate-700/80 backdrop-blur-md rounded-xl p-4 shadow-2xl animate-in slide-in-from-bottom-2 duration-200">
          <div className="flex items-start justify-between pb-2 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <span
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: selectedNode.color }}
              />
              <span className="text-xs font-mono uppercase tracking-wider text-slate-400">
                {selectedNode.label}
              </span>
            </div>
            <button
              onClick={() => setSelectedNode(null)}
              className="text-slate-400 hover:text-white"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <h4 className="text-sm font-semibold text-white mt-2 mb-1">{selectedNode.name}</h4>
          <p className="text-[11px] font-mono text-slate-400 mb-3">{selectedNode.id}</p>
          
          {selectedNode.properties && (
            <div className="space-y-1.5 text-xs bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/80 font-mono">
              {Object.entries(selectedNode.properties).map(([k, v]) => (
                <div key={k} className="flex flex-col text-[11px] pb-1 border-b border-slate-850 last:border-none">
                  <span className="text-slate-500">{k}:</span>
                  <span className="text-slate-200 truncate">{String(v)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Legend Footer */}
      <div className="absolute bottom-3 left-4 z-10 flex flex-wrap items-center gap-3 bg-slate-900/90 backdrop-blur-md border border-slate-800 rounded-lg px-3 py-2 text-[11px] text-slate-300 shadow-md">
        <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500 font-semibold">Nodes:</span>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-blue-500" />
          <span>Person</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
          <span>System</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-violet-500" />
          <span>Decision</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
          <span>Document</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-yellow-500" />
          <span>Evidence</span>
        </div>

        <div className="h-3 w-px bg-slate-800 mx-1" />

        <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500 font-semibold">Edges:</span>
        <div className="flex items-center gap-1.5">
          <span className="w-4 h-0.5 border-b-2 border-dashed border-red-500" />
          <span className="text-red-400 font-mono text-[10px]">[:SUPERSEDES]</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-4 h-0.5 bg-yellow-500" />
          <span className="text-yellow-400 font-mono text-[10px]">[:SUPPORTED_BY]</span>
        </div>
      </div>
    </main>
  );
};
