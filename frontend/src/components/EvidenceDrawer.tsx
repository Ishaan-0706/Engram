'use client';

import React, { useState } from 'react';
import { EvidenceItem } from '@/types';
import { 
  X, 
  Hash, 
  ExternalLink, 
  Clock, 
  FileText, 
  Check, 
  Copy, 
  ShieldCheck, 
  MessageSquare,
  BookOpen
} from 'lucide-react';

interface EvidenceDrawerProps {
  evidence: EvidenceItem | null;
  onClose: () => void;
  isOpen: boolean;
}

export const EvidenceDrawer: React.FC<EvidenceDrawerProps> = ({
  evidence,
  onClose,
  isOpen,
}) => {
  const [copied, setCopied] = useState(false);

  if (!isOpen || !evidence) return null;

  const handleCopyHash = () => {
    if (evidence?.content_hash) {
      navigator.clipboard.writeText(evidence.content_hash);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const isSlack = evidence.source_uri.startsWith('slack://');
  const isConfluence = evidence.source_uri.startsWith('confluence://');

  return (
    <div className="fixed inset-0 z-50 flex overflow-hidden">
      {/* Backdrop */}
      <div 
        className="fixed inset-0 bg-slate-950/70 backdrop-blur-sm transition-opacity animate-in fade-in duration-200"
        onClick={onClose}
      />

      {/* Slide-over panel */}
      <div className="relative w-full max-w-md bg-slate-900 border-r border-slate-700/80 text-slate-100 flex flex-col shadow-2xl z-10 animate-in slide-in-from-left duration-300">
        {/* Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/50">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-md bg-amber-500/20 text-amber-400 border border-amber-500/30 flex items-center justify-center">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                Grounded Evidence
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                  VERIFIED
                </span>
              </h2>
              <p className="text-[11px] font-mono text-slate-400 truncate max-w-[260px]">{evidence.id}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close Evidence Drawer"
            className="p-1.5 rounded-md text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* Verbatim Excerpt */}
          <div className="space-y-2">
            <span className="text-[11px] font-mono uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5 text-indigo-400" />
              Verbatim Source Excerpt
            </span>
            <div className="bg-slate-950/90 border border-slate-800 rounded-lg p-3.5 relative overflow-hidden">
              <div className="absolute left-0 top-0 bottom-0 w-1 bg-amber-500" />
              <blockquote className="text-xs leading-relaxed text-slate-200 italic pl-1 font-serif">
                &ldquo;{evidence.excerpt}&rdquo;
              </blockquote>
            </div>
          </div>

          {/* Source Location & Platform */}
          <div className="space-y-2">
            <span className="text-[11px] font-mono uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <ExternalLink className="w-3.5 h-3.5 text-indigo-400" />
              Source Provenance URI
            </span>
            <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-3 space-y-2">
              <div className="flex items-center gap-2">
                {isSlack ? (
                  <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded font-medium bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                    <MessageSquare className="w-3 h-3" />
                    Slack Enterprise
                  </span>
                ) : isConfluence ? (
                  <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded font-medium bg-blue-500/15 text-blue-400 border border-blue-500/30">
                    <BookOpen className="w-3 h-3" />
                    Confluence Wiki
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded font-medium bg-slate-800 text-slate-300">
                    Document Store
                  </span>
                )}
              </div>
              <p className="text-xs font-mono text-slate-300 break-all bg-slate-900 p-2 rounded border border-slate-800">
                {evidence.source_uri}
              </p>
            </div>
          </div>

          {/* Timestamp */}
          <div className="space-y-2">
            <span className="text-[11px] font-mono uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-indigo-400" />
              Source Ingestion Timestamp
            </span>
            <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-2.5 text-xs font-mono text-slate-300 flex items-center gap-2">
              <span className="text-slate-400">Recorded:</span>
              <span className="text-white font-medium">{evidence.source_timestamp}</span>
            </div>
          </div>

          {/* Cryptographic SHA-256 Hash */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-mono uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Hash className="w-3.5 h-3.5 text-indigo-400" />
                SHA-256 Content Hash
              </span>
              <button
                onClick={handleCopyHash}
                className="text-[11px] font-mono text-indigo-400 hover:text-indigo-300 flex items-center gap-1 transition-colors"
              >
                {copied ? (
                  <>
                    <Check className="w-3 h-3 text-emerald-400" />
                    <span className="text-emerald-400">Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3 h-3" />
                    Copy
                  </>
                )}
              </button>
            </div>
            <div className="bg-slate-950/90 border border-slate-800 rounded-lg p-2.5 font-mono text-[11px] text-amber-300/90 break-all select-all">
              {evidence.content_hash}
            </div>
          </div>

          {/* Connected Record ID */}
          <div className="space-y-1 pt-2 border-t border-slate-800">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-400">Associated Node ID:</span>
              <span className="font-mono text-slate-200 bg-slate-800 px-2 py-0.5 rounded text-[11px]">
                {evidence.record_id}
              </span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-800 bg-slate-950/50 flex justify-end">
          <button
            onClick={onClose}
            className="px-3.5 py-1.5 text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-md transition-colors"
          >
            Close Drawer
          </button>
        </div>
      </div>
    </div>
  );
};
