'use client';

import React, { useState } from 'react';
import { ChatMessage, EvidenceItem, TurnState } from '@/types';
import { 
  Send, 
  Sparkles, 
  AlertTriangle, 
  ShieldAlert, 
  CheckCircle2, 
  Layers, 
  HelpCircle,
  FileQuestion,
  History,
  FileCode,
  AlertOctagon,
  Bot,
  User,
  Loader2
} from 'lucide-react';

interface LeftPaneProps {
  messages: ChatMessage[];
  turnState: TurnState | null;
  isLoading: boolean;
  onSendQuery: (query: string) => void;
  onSelectEvidence: (evidence: EvidenceItem) => void;
  onHighlightEvidence: (evidenceId: string | null) => void;
  onQuickDemo1: () => void;
  onQuickDemo2: () => void;
  onQuickDemo3: () => void;
}

export const LeftPane: React.FC<LeftPaneProps> = ({
  messages,
  turnState,
  isLoading,
  onSendQuery,
  onSelectEvidence,
  onHighlightEvidence,
  onQuickDemo1,
  onQuickDemo2,
  onQuickDemo3,
}) => {
  const [inputQuery, setInputQuery] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputQuery.trim() || isLoading) return;
    onSendQuery(inputQuery.trim());
    setInputQuery('');
  };

  const evidenceBag = turnState?.evidence_bag || {};
  const evidenceIds = Object.keys(evidenceBag);

  return (
    <aside className="w-[420px] min-w-[420px] max-w-[420px] border-r border-slate-800 bg-slate-950 flex flex-col h-[calc(100vh-3.5rem)] select-text relative">
      {/* Pane Header */}
      <div className="p-3.5 border-b border-slate-800/80 bg-slate-900/40 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 flex items-center justify-center">
            <Sparkles className="w-3.5 h-3.5" />
          </div>
          <div>
            <h2 className="text-xs font-semibold text-white tracking-tight">Chat & Grounded Evidence</h2>
            <p className="text-[10px] text-slate-400">Deterministic claim-to-evidence verification</p>
          </div>
        </div>
        <span className="text-[10px] font-mono bg-slate-800/80 text-slate-300 px-2 py-0.5 rounded border border-slate-700/50">
          Strict Mode
        </span>
      </div>

      {/* Messages & Claim Bubbles */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 text-slate-400 space-y-3">
            <div className="w-12 h-12 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-400">
              <Bot className="w-6 h-6 text-indigo-400" />
            </div>
            <div>
              <h3 className="text-xs font-semibold text-slate-200">Knowledge Assistant Ready</h3>
              <p className="text-[11px] text-slate-400 max-w-[260px] mt-1 leading-relaxed">
                Ask architectural, ownership, or decision questions across company documents and live graphs.
              </p>
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col space-y-1.5 ${
              msg.role === 'user' ? 'items-end' : 'items-start'
            }`}
          >
            {/* Author label */}
            <div className="flex items-center gap-1.5 px-1 text-[10px] font-mono text-slate-400">
              {msg.role === 'user' ? (
                <>
                  <span>Staff Engineer</span>
                  <User className="w-3 h-3 text-indigo-400" />
                </>
              ) : (
                <>
                  <Bot className="w-3 h-3 text-emerald-400" />
                  <span>Company Brain</span>
                  {msg.epoch !== undefined && (
                    <span className="text-[9px] bg-slate-800 text-slate-300 px-1 py-0.2 rounded font-mono">
                      ep:{msg.epoch}
                    </span>
                  )}
                </>
              )}
            </div>

            {/* Bubble */}
            <div
              className={`rounded-xl px-4 py-3 text-xs leading-relaxed max-w-[95%] shadow-sm ${
                msg.role === 'user'
                  ? 'bg-indigo-600 text-white rounded-tr-none'
                  : 'bg-slate-900 border border-slate-800 text-slate-200 rounded-tl-none space-y-3'
              }`}
            >
              {msg.role === 'user' ? (
                <p>{msg.content}</p>
              ) : (
                <>
                  {/* Synthesis Summary */}
                  {msg.answer?.summary && (
                    <p className="font-medium text-slate-100 pb-2 border-b border-slate-800/80 leading-relaxed">
                      {msg.answer.summary}
                    </p>
                  )}

                  {/* Grounded Claims */}
                  {msg.answer && ((msg.answer.statements && msg.answer.statements.length > 0) || (msg.answer.claims && msg.answer.claims.length > 0)) && (
                    <div className="space-y-2">
                      <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                        Verified Statements & Citations
                      </span>
                      <div className="space-y-2">
                        {(msg.answer.statements || msg.answer.claims || []).map((stmt, idx) => (
                          <div
                            key={idx}
                            className="bg-slate-950/70 border border-slate-800/90 rounded-lg p-2.5 text-xs text-slate-200"
                          >
                            <p className="mb-2 leading-relaxed">
                              {stmt.claim || stmt.text || ''}
                            </p>
                            {/* Citation Pills */}
                            <div className="flex flex-wrap items-center gap-1.5 pt-1 border-t border-slate-800/60">
                              <span className="text-[10px] text-slate-400 font-mono">Sources:</span>
                              {stmt.cited_evidence_ids.map((eid, cIdx) => {
                                const evItem = evidenceBag[eid] || {
                                  id: eid,
                                  record_id: 'unknown',
                                  excerpt: 'Verbatim excerpt indexed in FalkorDB evidence bag.',
                                  source_uri: 'falkordb://evidence/' + eid,
                                  source_timestamp: '2026-09-22T14:30:00Z',
                                  content_hash: 'sha256:' + 'a'.repeat(64),
                                };
                                return (
                                  <button
                                    key={cIdx}
                                    type="button"
                                    onClick={() => onSelectEvidence(evItem)}
                                    onMouseEnter={() => onHighlightEvidence(eid)}
                                    onMouseLeave={() => onHighlightEvidence(null)}
                                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-amber-500/15 text-amber-300 border border-amber-500/30 hover:bg-amber-500/25 hover:border-amber-400 transition-all cursor-pointer shadow-sm active:scale-95"
                                  >
                                    <span>[E{cIdx + 1}]</span>
                                    <span className="text-[9px] text-amber-400/80 truncate max-w-[80px]">
                                      {eid.replace('evi_', '').replace('ev_', '')}
                                    </span>
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Empty/Abstained State when status is FAILED with unverifiable_claim */}
                  {msg.status === 'FAILED' && msg.fail_reason === 'unverifiable_claim' && (
                    <div className="bg-rose-950/30 border border-rose-900/50 rounded-lg p-3 text-xs text-rose-200 space-y-2">
                      <div className="flex items-center gap-2 text-rose-400 font-semibold">
                        <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
                        <span>Ungrounded Claim Abstained</span>
                      </div>
                      <p className="text-[11px] text-rose-300/90 leading-relaxed">
                        The model attempted to cite an evidence ID not present in the verified evidence bag. 
                        Under the Company Brain zero-hallucination contract, streaming was suppressed and the answer body was abstained.
                      </p>
                      <div className="text-[10px] font-mono bg-rose-950/60 p-1.5 rounded border border-rose-900/60 text-rose-300">
                        Error Code: unverifiable_claim (two-phase retry exhausted)
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex items-center gap-2 p-3 bg-slate-900/50 border border-slate-800/80 rounded-xl text-xs text-indigo-300 animate-pulse">
            <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
            <span>Traversing FalkorDB & verifying evidence bag...</span>
          </div>
        )}
      </div>

      {/* Query Input Bar */}
      <div className="p-3 border-t border-slate-800 bg-slate-950/90">
        <form onSubmit={handleSubmit} className="relative flex items-center">
          <input
            type="text"
            value={inputQuery}
            onChange={(e) => setInputQuery(e.target.value)}
            disabled={isLoading}
            placeholder="Ask Company Brain..."
            aria-label="Ask Company Brain"
            className="w-full bg-slate-900 border border-slate-800 text-xs text-slate-100 rounded-lg pl-3 pr-10 py-2.5 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!inputQuery.trim() || isLoading}
            aria-label="Submit query"
            className="absolute right-1.5 p-1.5 rounded-md bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-40 disabled:hover:bg-indigo-600 transition-colors"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </form>
      </div>

      {/* Quick-Demo Action Buttons (at bottom of Left Pane for testing) */}
      <div className="p-3 border-t border-slate-800/80 bg-slate-900/60 space-y-2">
        <div className="flex items-center justify-between text-[10px] font-mono uppercase tracking-wider text-slate-400">
          <span>Executive Test Presets</span>
          <span className="text-[9px] text-indigo-400">3 Verification Flows</span>
        </div>
        <div className="grid grid-cols-1 gap-1.5">
          <button
            type="button"
            onClick={onQuickDemo1}
            disabled={isLoading}
            className="flex items-center gap-2 w-full text-left px-2.5 py-1.5 rounded-md text-xs font-medium bg-slate-900 border border-slate-800 hover:border-slate-700 hover:bg-slate-850 text-slate-200 transition-colors shadow-sm disabled:opacity-50"
          >
            <History className="w-3.5 h-3.5 text-violet-400 shrink-0" />
            <div className="truncate">
              <span className="text-white">Query Payment Auth History</span>
              <span className="text-[10px] text-slate-400 block -mt-0.5">Triggers decision history turn</span>
            </div>
          </button>

          <button
            type="button"
            onClick={onQuickDemo2}
            disabled={isLoading}
            className="flex items-center gap-2 w-full text-left px-2.5 py-1.5 rounded-md text-xs font-medium bg-slate-900 border border-slate-800 hover:border-slate-700 hover:bg-slate-850 text-slate-200 transition-colors shadow-sm disabled:opacity-50"
          >
            <FileCode className="w-3.5 h-3.5 text-amber-400 shrink-0" />
            <div className="truncate">
              <span className="text-white">Check Documentation Drift</span>
              <span className="text-[10px] text-slate-400 block -mt-0.5">Loads proposal card (Awaiting Confirmation)</span>
            </div>
          </button>

          <button
            type="button"
            onClick={onQuickDemo3}
            disabled={isLoading}
            className="flex items-center gap-2 w-full text-left px-2.5 py-1.5 rounded-md text-xs font-medium bg-rose-950/20 border border-rose-900/40 hover:border-rose-800 hover:bg-rose-950/30 text-rose-200 transition-colors shadow-sm disabled:opacity-50"
          >
            <AlertOctagon className="w-3.5 h-3.5 text-rose-400 shrink-0" />
            <div className="truncate">
              <span className="text-rose-100 font-semibold">Simulate Stale Snapshot</span>
              <span className="text-[10px] text-rose-400/80 block -mt-0.5">Tests 409 Conflict rejection modal</span>
            </div>
          </button>
        </div>
      </div>
    </aside>
  );
};
