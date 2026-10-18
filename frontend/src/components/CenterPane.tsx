'use client';

import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { forceCollide } from 'd3-force';
import { GraphLink, GraphNode } from '@/types';
import { 
  Maximize2, 
  ZoomIn, 
  ZoomOut, 
  Sparkles,
  X,
  Crosshair,
  AlertTriangle
} from 'lucide-react';

// Dynamic import with SSR disabled since react-force-graph-2d requires browser window & canvas
const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { 
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex flex-col items-center justify-center bg-[#13151A] text-[#949BA6] gap-3">
      <div className="w-6 h-6 rounded-full border-2 border-[#4C78A8]/40 border-t-[#4C78A8] animate-spin" />
      <span className="text-xs font-mono tracking-tight text-[#858D9A]">Initializing Force Topology...</span>
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
  const hasAutoFittedRef = useRef(false);

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

  // Configure D3 Force Physics:
  // d3VelocityDecay(0.32), d3Force("charge").strength(-450), d3Force("link").distance(140), d3Force("collide", d3.forceCollide(40))
  const configurePhysics = useCallback(() => {
    if (!fgRef.current) return;
    
    if (typeof fgRef.current.d3VelocityDecay === 'function') {
      fgRef.current.d3VelocityDecay(0.32);
    }
    
    if (typeof fgRef.current.d3Force === 'function') {
      const charge = fgRef.current.d3Force('charge');
      if (charge && typeof charge.strength === 'function') {
        charge.strength(-450);
      }
      
      const link = fgRef.current.d3Force('link');
      if (link && typeof link.distance === 'function') {
        link.distance(140);
      }
      
      fgRef.current.d3Force('collide', forceCollide(40));
    }

    if (typeof fgRef.current.d3ReheatSimulation === 'function') {
      fgRef.current.d3ReheatSimulation();
    }
  }, []);

  useEffect(() => {
    hasAutoFittedRef.current = false;
    configurePhysics();
    const t1 = setTimeout(configurePhysics, 200);
    const t2 = setTimeout(() => {
      if (!hasAutoFittedRef.current && fgRef.current) {
        fgRef.current.zoomToFit(400, 70);
        hasAutoFittedRef.current = true;
      }
    }, 600);

    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [nodes, links, configurePhysics]);

  // Expose node position query helper for Playwright presenter cursor & node interactions
  useEffect(() => {
    if (typeof window !== 'undefined') {
      (window as any).__companyBrainFg = fgRef.current;
      (window as any).__graphNodes = nodes;
      (window as any).__onNodeClick = onNodeClick;
      (window as any).__getNodeCoords = (query: string) => {
        const fg = fgRef.current;
        if (!fg || !nodes) return null;
        const q = query.toLowerCase();
        const node = nodes.find(
          (n: any) =>
            (n.id && n.id.toLowerCase() === q) ||
            (n.id && n.id.toLowerCase().includes(q)) ||
            (n.name && n.name.toLowerCase().includes(q))
        );
        if (!node || node.x === undefined || node.y === undefined) return null;
        const canvas = document.querySelector('canvas');
        if (!canvas) return null;
        const rect = canvas.getBoundingClientRect();
        const screenPos = typeof fg.graph2ScreenCoords === 'function' ? fg.graph2ScreenCoords(node.x, node.y) : null;
        if (!screenPos) return null;
        return {
          x: Math.round(rect.left + screenPos.x),
          y: Math.round(rect.top + screenPos.y),
          node,
        };
      };
    }
  }, [nodes, onNodeClick]);

  // Compute active highlight path: System -> Decision -> Evidence
  const highlightSet = useMemo(() => {
    const nodeIds = new Set<string>();
    const linkKeys = new Set<string>();

    if (highlightedEvidenceId) {
      // 1. Evidence node
      nodeIds.add(highlightedEvidenceId);

      // 2. Decisions connected to this evidence via SUPPORTED_BY
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

      // 3. Systems connected to those decisions via AFFECTS, DOCUMENTS, or ALIGNED_WITH
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

  // Custom Node & Label Renderer (nodeCanvasObject):
  // Understated circular node (radius: 8px) with a 1.5px border matching its entity type.
  // Directly below the node, pill container with background #191C23, 1px border of #2A2F3B, 4px horizontal padding, clean sans-serif text (10px, #E4E7EB).
  const drawNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const isHighlighted = highlightSet.isHoverActive && highlightSet.nodeIds.has(node.id);
      const isDimmed = highlightSet.isHoverActive && !highlightSet.nodeIds.has(node.id);

      ctx.save();
      // Hovering dims non-relevant nodes in the center graph to 20% opacity
      ctx.globalAlpha = isDimmed ? 0.2 : 1.0;

      const radius = isHighlighted ? 9.5 : 8;

      // Subtle focus outer ring for highlighted path nodes
      if (isHighlighted) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius + 3, 0, 2 * Math.PI, false);
        ctx.lineWidth = 1;
        ctx.strokeStyle = '#E4E7EB';
        ctx.stroke();
      }

      // Solid circular node
      ctx.beginPath();
      ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
      ctx.fillStyle = node.color || '#4C78A8';
      ctx.fill();

      // 1.5px border matching its entity type
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = isHighlighted ? '#E4E7EB' : (node.color || '#4C78A8');
      ctx.stroke();

      // Directly below the node, pill container badge: background #191C23, 1px border #2A2F3B, 4px horizontal padding, 10px #E4E7EB text
      if (globalScale >= 0.55 || isHighlighted) {
        const label = node.name || node.id;
        const fontSize = 10;
        ctx.font = `500 ${fontSize}px Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
        
        const textWidth = ctx.measureText(label).width;
        const padX = 4; // 4px horizontal padding
        const pillW = textWidth + padX * 2;
        const pillH = fontSize + 6;
        const pillX = node.x - pillW / 2;
        const pillY = node.y + radius + 4;
        const pillRadius = 3;

        // Background pill: #191C23
        ctx.beginPath();
        if (typeof ctx.roundRect === 'function') {
          ctx.roundRect(pillX, pillY, pillW, pillH, pillRadius);
        } else {
          ctx.rect(pillX, pillY, pillW, pillH);
        }
        ctx.fillStyle = '#191C23';
        ctx.fill();

        // 1px border: #2A2F3B (or #E4E7EB if highlighted)
        ctx.lineWidth = 1;
        ctx.strokeStyle = isHighlighted ? '#E4E7EB' : '#2A2F3B';
        ctx.stroke();

        // Clean sans-serif text (10px, #E4E7EB)
        ctx.fillStyle = isHighlighted ? '#FFFFFF' : '#E4E7EB';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(label, node.x, pillY + pillH / 2);
      }

      ctx.restore();
    },
    [highlightSet]
  );

  // Link Semantics:
  // - [:SUPERSEDES]: Muted Brick Red dashed line (#B84A39, [4, 4] dash) with directional arrowhead.
  // - [:SUPPORTED_BY]: Solid Indigo Slate stroke (#5E60CE, 1.5px).
  // - [:OWNS], [:DOCUMENTS], [:AFFECTS]: Subdued Iron Gray (#323744, 1px).
  const drawLink = useCallback(
    (link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const sId = typeof link.source === 'object' ? link.source.id : link.source;
      const tId = typeof link.target === 'object' ? link.target.id : link.target;
      const linkKey = `${sId}->${tId}`;

      const isPathLink = highlightSet.isHoverActive && highlightSet.linkKeys.has(linkKey);
      const isDimmed = highlightSet.isHoverActive && !isPathLink;

      ctx.save();
      // 20% opacity for non-relevant links
      ctx.globalAlpha = isDimmed ? 0.2 : (isPathLink ? 1.0 : 0.75);

      const sx = link.source.x;
      const sy = link.source.y;
      const tx = link.target.x;
      const ty = link.target.y;

      const isSupersedes = link.type === 'SUPERSEDES' || link.dashed;
      const isSupportedBy = link.type === 'SUPPORTED_BY';

      ctx.beginPath();
      ctx.moveTo(sx, sy);
      ctx.lineTo(tx, ty);

      if (isSupersedes) {
        // [:SUPERSEDES] Muted Brick Red dashed line (#B84A39, [4, 4] dash)
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = '#B84A39';
        ctx.lineWidth = isPathLink ? 2 : 1.2;
      } else if (isSupportedBy) {
        // [:SUPPORTED_BY] Solid Indigo Slate stroke (#5E60CE, 1.5px)
        ctx.setLineDash([]);
        ctx.strokeStyle = '#5E60CE';
        ctx.lineWidth = isPathLink ? 2.5 : 1.5;
      } else {
        // [:OWNS], [:DOCUMENTS], [:AFFECTS] Subdued Iron Gray (#323744, 1px)
        ctx.setLineDash([]);
        ctx.strokeStyle = isPathLink ? '#4C78A8' : (link.color || '#323744');
        ctx.lineWidth = isPathLink ? 1.8 : 1.0;
      }

      ctx.stroke();

      // Directional arrowhead for [:SUPERSEDES]
      if (isSupersedes) {
        const dx = tx - sx;
        const dy = ty - sy;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist > 18) {
          const ux = dx / dist;
          const uy = dy / dist;
          const targetRadius = 12;
          const tipX = tx - ux * targetRadius;
          const tipY = ty - uy * targetRadius;
          const angle = Math.atan2(dy, dx);
          const arrowLength = 7;

          ctx.setLineDash([]);
          ctx.beginPath();
          ctx.moveTo(tipX, tipY);
          ctx.lineTo(
            tipX - arrowLength * Math.cos(angle - Math.PI / 6),
            tipY - arrowLength * Math.sin(angle - Math.PI / 6)
          );
          ctx.lineTo(
            tipX - arrowLength * Math.cos(angle + Math.PI / 6),
            tipY - arrowLength * Math.sin(angle + Math.PI / 6)
          );
          ctx.closePath();
          ctx.fillStyle = '#B84A39';
          ctx.fill();
        }
      }

      // Link relation label on hover or high zoom
      if (globalScale > 1.3 || isPathLink) {
        const midX = (sx + tx) / 2;
        const midY = (sy + ty) / 2;
        ctx.font = `400 ${Math.max(8, 8.5 / globalScale)}px monospace`;
        ctx.fillStyle = isPathLink ? '#E4E7EB' : '#858D9A';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';
        ctx.fillText(`[:${link.type || link.label}]`, midX, midY - 2);
      }

      ctx.restore();
    },
    [highlightSet]
  );

  return (
    <main className="flex-1 h-[calc(100vh-3.5rem)] bg-[#13151A] flex flex-col relative overflow-hidden select-none">
      {/* Path Illumination Indicator */}
      {highlightSet.isHoverActive && (
        <div className="absolute top-3 right-4 z-10 bg-[#191C23] border border-[#2A2F3B] rounded px-3 py-1.5 text-xs text-[#E4E7EB] flex items-center gap-2 shadow-sm animate-in fade-in duration-150">
          <Sparkles className="w-3.5 h-3.5 text-[#5E60CE]" />
          <span className="font-mono text-[11px] text-[#949BA6]">
            Path: <span className="text-[#4C78A8] font-semibold">System</span> → <span className="text-[#4E9F76] font-semibold">Decision</span> → <span className="text-[#5E60CE] font-semibold">Evidence</span>
          </span>
        </div>
      )}

      {/* Force Graph Canvas Container */}
      <div ref={containerRef} className="flex-1 w-full h-full cursor-grab active:cursor-grabbing">
        {dimensions.width > 0 && dimensions.height > 0 && (
          nodes.length > 0 ? (
            <ForceGraph2D
              ref={fgRef}
              width={dimensions.width}
              height={dimensions.height}
              graphData={{ nodes, links }}
              nodeCanvasObject={drawNode}
              linkCanvasObject={drawLink}
              backgroundColor="#13151A"
              d3VelocityDecay={0.32}
              cooldownTicks={120}
              onEngineStop={() => {
                if (!hasAutoFittedRef.current && fgRef.current) {
                  fgRef.current.zoomToFit(400, 70);
                  hasAutoFittedRef.current = true;
                }
              }}
              onNodeClick={(node: any) => {
                setSelectedNode(node);
                if (onNodeClick) onNodeClick(node);
              }}
            />
          ) : (
            <div className="w-full h-full flex flex-col items-center justify-center p-8 text-center gap-3">
              <div className="w-12 h-12 rounded-full bg-[#B84A39]/15 border border-[#B84A39]/40 flex items-center justify-center text-[#B84A39]">
                <AlertTriangle className="w-6 h-6" />
              </div>
              <h3 className="text-sm font-semibold text-[#E4E7EB]">FalkorDB Connection Required</h3>
              <p className="text-xs text-[#949BA6] max-w-md leading-relaxed">
                Start FalkorDB on port 6379 to load live graph topology. Zero mock fallbacks active.
              </p>
              <code className="text-[11px] font-mono bg-[#191C23] border border-[#2A2F3B] px-3 py-1.5 rounded text-[#D07D38]">
                docker run -p 6379:6379 -it --rm falkordb/falkordb:latest
              </code>
            </div>
          )
        )}
      </div>

      {/* Interaction Controls: Floating zoom control dock in bottom-right corner */}
      <div className="absolute bottom-4 right-4 z-10 flex items-center gap-1 bg-[#191C23] border border-[#2A2F3B] rounded-md p-1 shadow-md">
        <button
          onClick={() => fgRef.current?.zoom(fgRef.current.zoom() * 1.3, 250)}
          title="Zoom In"
          aria-label="Zoom In"
          className="p-1.5 rounded text-[#949BA6] hover:text-[#E4E7EB] hover:bg-[#20242D] transition-colors"
        >
          <ZoomIn className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => fgRef.current?.zoom(fgRef.current.zoom() / 1.3, 250)}
          title="Zoom Out"
          aria-label="Zoom Out"
          className="p-1.5 rounded text-[#949BA6] hover:text-[#E4E7EB] hover:bg-[#20242D] transition-colors"
        >
          <ZoomOut className="w-3.5 h-3.5" />
        </button>
        <div className="w-px h-3.5 bg-[#2A2F3B] mx-0.5" />
        <button
          onClick={() => fgRef.current?.zoomToFit(400, 70)}
          title="Center View"
          aria-label="Center View"
          className="p-1.5 rounded text-[#949BA6] hover:text-[#E4E7EB] hover:bg-[#20242D] transition-colors flex items-center gap-1 text-[11px] font-mono"
        >
          <Crosshair className="w-3.5 h-3.5" />
          <span>Center</span>
        </button>
      </div>

      {/* Selected Node Details Card Overlay */}
      {selectedNode && (
        <div className="absolute top-3 left-4 z-20 w-80 bg-[#191C23] border border-[#2A2F3B] rounded-lg p-3.5 shadow-xl animate-in fade-in duration-150">
          <div className="flex items-start justify-between pb-2 border-b border-[#2A2F3B]">
            <div className="flex items-center gap-2">
              <span
                className="w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: selectedNode.color }}
              />
              <span className="text-[10px] font-mono uppercase tracking-wider text-[#949BA6] font-semibold">
                {selectedNode.label} Inspector
              </span>
            </div>
            <button
              onClick={() => setSelectedNode(null)}
              className="text-[#949BA6] hover:text-[#E4E7EB]"
              aria-label="Close details"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <h4 className="text-xs font-semibold text-[#E4E7EB] mt-2 mb-0.5">{selectedNode.name}</h4>
          <p className="text-[10px] font-mono text-[#858D9A] mb-2.5">{selectedNode.id}</p>
          
          {selectedNode.properties && (
            <div className="space-y-1 text-xs bg-[#20242D] p-2 rounded border border-[#2A2F3B] font-mono">
              {Object.entries(selectedNode.properties).map(([k, v]) => (
                <div key={k} className="flex flex-col text-[10px] pb-1 border-b border-[#2A2F3B] last:border-none last:pb-0">
                  <span className="text-[#949BA6]">{k}:</span>
                  <span className="text-[#E4E7EB] truncate">{String(v)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Clean Bottom-Left Legend */}
      <div className="absolute bottom-4 left-4 z-10 flex flex-wrap items-center gap-3 bg-[#191C23] border border-[#2A2F3B] rounded-md px-3 py-1.5 text-[11px] text-[#949BA6] shadow-sm">
        <span className="text-[10px] font-mono uppercase tracking-wider text-[#858D9A] font-semibold">Nodes:</span>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[#D4CEBF]" />
          <span className="text-[#E4E7EB]">Person</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[#4C78A8]" />
          <span className="text-[#E4E7EB]">System</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[#4E9F76]" />
          <span className="text-[#E4E7EB]">Decision (Active)</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[#68707E]" />
          <span className="text-[#E4E7EB] line-through">Superseded</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[#D07D38]" />
          <span className="text-[#E4E7EB]">Drift</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[#5E60CE]" />
          <span className="text-[#E4E7EB]">Evidence</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[#949BA6]" />
          <span className="text-[#E4E7EB]">Team</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[#858D9A]" />
          <span className="text-[#E4E7EB]">Project</span>
        </div>

        <div className="h-3 w-px bg-[#2A2F3B] mx-1" />

        <span className="text-[10px] font-mono uppercase tracking-wider text-[#858D9A] font-semibold">Edges:</span>
        <div className="flex items-center gap-1.5">
          <span className="w-3.5 h-0.5 border-b border-dashed border-[#B84A39]" />
          <span className="text-[#B84A39] font-mono text-[10px]">[:SUPERSEDES]</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3.5 h-0.5 bg-[#5E60CE]" />
          <span className="text-[#5E60CE] font-mono text-[10px]">[:SUPPORTED_BY]</span>
        </div>
      </div>
    </main>
  );
};
