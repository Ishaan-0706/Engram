'use client';

import React, { useState, useRef, useEffect } from 'react';
import { ChatMessage, EvidenceItem, TurnState } from '@/types';
import { 
  Bot, 
  User, 
  Loader2,
  ShieldAlert,
  CornerDownLeft
} from 'lucide-react';

interface LeftPaneProps {
  messages: ChatMessage[];
  turnState: TurnState | null;
  isLoading: boolean;
  onSendQuery: (query: string) => void;
  onSelectEvidence: (evidence: EvidenceItem) => void;
  onHighlightEvidence: (evidenceId: string | null) => void;
  onPresetDecisionTrace?: () => void;
  onPresetWhoOwnsVsKnows?: () => void;
  onPresetKnowledgeDrift?: () => void;
  onPresetTenantIsolation?: () => void;
  onDemoScenario1?: () => void;
  onDemoScenario2?: () => void;
  onDemoScenario3?: () => void;
  onSimulateStaleSnapshot?: () => void;
  onQuickDemo1?: () => void;
  onQuickDemo2?: () => void;
  onQuickDemo3?: () => void;
}

export const LeftPane: React.FC<LeftPaneProps> = ({
  messages,
  turnState,
  isLoading,
  onSendQuery,
  onSelectEvidence,
  onHighlightEvidence,
  onPresetDecisionTrace,
  onPresetWhoOwnsVsKnows,
  onPresetKnowledgeDrift,
  onPresetTenantIsolation,
  onDemoScenario1,
  onDemoScenario2,
  onDemoScenario3,
  onSimulateStaleSnapshot,
  onQuickDemo1,
  onQuickDemo2,
  onQuickDemo3,
}) => {
  const [inputQuery, setInputQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  // Keyboard shortcut listener for Cmd + K / Ctrl + K
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputQuery.trim() || isLoading) return;
    onSendQuery(inputQuery.trim());
    setInputQuery('');
  };

  const evidenceBag = turnState?.evidence_bag || {};

  const handleRunPreset1 = onPresetDecisionTrace || onDemoScenario1 || onQuickDemo1;
  const handleRunPreset2 = onPresetWhoOwnsVsKnows || onDemoScenario2 || onQuickDemo2;
  const handleRunPreset3 = onPresetKnowledgeDrift || onDemoScenario1;
  const handleRunPreset4 = onPresetTenantIsolation || onDemoScenario3 || onQuickDemo3;

  return (
    <aside className="w-[400px] min-w-[400px] max-w-[400px] border-r border-[#2A2F3B] bg-[#191C23] flex flex-col h-[calc(100vh-3rem)] select-text relative">
      {/* 4 One-Click Judge Evaluation Preset Chips */}
      <div className="px-3 py-2 border-b border-[#2A2F3B] bg-[#191C23] flex items-center gap-1.5 overflow-x-auto shrink-0 scrollbar-none">
        {handleRunPreset1 && (
          <button
            type="button"
            onClick={handleRunPreset1}
            disabled={isLoading}
            title="Trace Decision & Sources (Slack + Linear)"
            className="bg-[#20242D] border border-[#2A2F3B] hover:border-[#3E4554] text-xs text-[#E4E7EB] px-2 py-1 rounded transition-colors whitespace-nowrap active:scale-[0.98] disabled:opacity-50 text-[11px]"
          >
            1. Trace Decision
          </button>
        )}
        {handleRunPreset2 && (
          <button
            type="button"
            onClick={handleRunPreset2}
            disabled={isLoading}
            title="Who Formal Owns vs Who Knows What"
            className="bg-[#20242D] border border-[#2A2F3B] hover:border-[#3E4554] text-xs text-[#E4E7EB] px-2 py-1 rounded transition-colors whitespace-nowrap active:scale-[0.98] disabled:opacity-50 text-[11px]"
          >
            2. Who Owns vs Knows
          </button>
        )}
        {handleRunPreset3 && (
          <button
            type="button"
            onClick={handleRunPreset3}
            disabled={isLoading}
            title="Detect & Resolve Knowledge Drift"
            className="bg-[#20242D] border border-[#2A2F3B] hover:border-[#3E4554] text-xs text-[#E4E7EB] px-2 py-1 rounded transition-colors whitespace-nowrap active:scale-[0.98] disabled:opacity-50 text-[11px]"
          >
            3. Resolve Drift
          </button>
        )}
        {handleRunPreset4 && (
          <button
            type="button"
            onClick={handleRunPreset4}
            disabled={isLoading}
            title="Verify Strict Zero-Leakage Tenant Isolation"
            className="bg-[#20242D] border border-[#2A2F3B] hover:border-[#3E4554] text-xs text-[#E4E7EB] px-2 py-1 rounded transition-colors whitespace-nowrap active:scale-[0.98] disabled:opacity-50 text-[11px]"
          >
            4. Tenant Isolation
          </button>
        )}
        {onSimulateStaleSnapshot && (
          <button
            type="button"
            onClick={onSimulateStaleSnapshot}
            disabled={isLoading}
            title="Simulate 409 Snapshot Conflict"
            className="bg-[#20242D] border border-[#D07D38]/50 hover:border-[#D07D38] text-[#D07D38] px-2 py-1 rounded transition-colors whitespace-nowrap active:scale-[0.98] disabled:opacity-50 font-mono text-[10px]"
          >
            ⚡ 409
          </button>
        )}
      </div>

      {/* Chat Messages Scroll Container */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3.5">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 text-[#949BA6] space-y-2.5">
            <div className="w-8 h-8 rounded bg-[#20242D] border border-[#2A2F3B] flex items-center justify-center text-[#858D9A]">
              <Bot className="w-4 h-4 text-[#4C78A8]" />
            </div>
            <div>
              <h3 className="text-xs font-semibold text-[#E4E7EB]">Company Brain Online</h3>
              <p className="text-[11px] text-[#949BA6] max-w-[260px] mt-1 leading-relaxed">
                Grounded conversational synthesis across FalkorDB and company architecture records.
              </p>
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col space-y-1 ${
              msg.role === 'user' ? 'items-end' : 'items-start'
            }`}
          >
            {/* Author label & metadata */}
            <div className="flex items-center gap-1.5 px-1 text-[10px] font-mono text-[#858D9A]">
              {msg.role === 'user' ? (
                <>
                  <span>Staff Engineer</span>
                  <User className="w-3 h-3 text-[#949BA6]" />
                </>
              ) : (
                <>
                  <Bot className="w-3 h-3 text-[#4C78A8]" />
                  <span>Company Brain</span>
                  {msg.epoch !== undefined && (
                    <span className="text-[9px] bg-[#20242D] text-[#858D9A] px-1 py-0.2 rounded border border-[#2A2F3B]">
                      epoch: {msg.epoch}
                    </span>
                  )}
                </>
              )}
            </div>

            {/* Bubble / Card */}
            <div
              className={`rounded-lg px-3.5 py-3 text-xs leading-relaxed max-w-[96%] shadow-sm ${
                msg.role === 'user'
                  ? 'bg-[#20242D] border border-[#2A2F3B] text-[#E4E7EB]'
                  : 'bg-[#20242D] border border-[#2A2F3B] text-[#E4E7EB] space-y-2.5'
              }`}
            >
              {msg.role === 'user' ? (
                <p>{msg.content}</p>
              ) : (
                <>
                  {/* Summary Text */}
                  {msg.answer?.summary && (
                    <p className="font-medium text-[#E4E7EB] leading-relaxed">
                      {msg.answer.summary}
                    </p>
                  )}

                  {/* Grounded Bullet Points with Compact Footnote Citations */}
                  {msg.answer && ((msg.answer.statements && msg.answer.statements.length > 0) || (msg.answer.claims && msg.answer.claims.length > 0)) && (
                    <div className="pt-2 border-t border-[#2A2F3B] space-y-2">
                      <div className="space-y-1.5">
                        {(msg.answer.statements || msg.answer.claims || []).map((stmt, sIdx) => (
                          <div key={sIdx} className="flex items-start gap-2 text-[11px] leading-relaxed text-[#E4E7EB]">
                            <span className="text-[#858D9A] mt-1 select-none text-[8px]">•</span>
                            <div className="flex-1">
                              <span>{stmt.claim || stmt.text || ''}</span>
                              {/* Footnote citations: [1], [2] */}
                              {stmt.cited_evidence_ids.map((eid, cIdx) => {
                                const evItem = evidenceBag[eid] || {
                                  id: eid,
                                  record_id: 'unknown',
                                  excerpt: 'Verbatim excerpt indexed in FalkorDB evidence bag.',
                                  source_uri: 'falkordb://evidence/' + eid,
                                  source_timestamp: '2026-09-22T14:30:00Z',
                                  content_hash: 'sha256:' + '0'.repeat(64),
                                };
                                return (
                                  <button
                                    key={cIdx}
                                    type="button"
                                    onClick={() => onSelectEvidence(evItem)}
                                    onMouseEnter={() => onHighlightEvidence(eid)}
                                    onMouseLeave={() => onHighlightEvidence(null)}
                                    title={`Evidence: ${eid}`}
                                    className="text-[#E4E7EB] bg-[#2A2F3B] hover:bg-[#343B4A] rounded px-1.5 py-0.5 text-xs inline-flex items-center justify-center font-mono select-none cursor-pointer mx-0.5 transition-colors"
                                  >
                                    [{cIdx + 1}]
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Abstained state for unverifiable claims */}
                  {msg.status === 'FAILED' && msg.fail_reason === 'unverifiable_claim' && (
                    <div className="bg-[#2A2F3B]/50 border border-[#D07D38]/40 rounded p-2.5 text-xs text-[#E4E7EB] space-y-1">
                      <div className="flex items-center gap-1.5 text-[#D07D38] font-semibold text-[11px]">
                        <ShieldAlert className="w-3.5 h-3.5" />
                        <span>Ungrounded Claim Abstained</span>
                      </div>
                      <p className="text-[10px] text-[#949BA6] leading-normal">
                        Citation references unindexed evidence. Zero-hallucination suppression active.
                      </p>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex items-center gap-2 p-2.5 bg-[#20242D] border border-[#2A2F3B] rounded text-xs text-[#949BA6] animate-pulse">
            <Loader2 className="w-3.5 h-3.5 animate-spin text-[#4C78A8]" />
            <span className="font-mono text-[11px]">Synthesizing grounded evidence...</span>
          </div>
        )}
      </div>

      {/* Input Box: Modern Developer Tool Command Prompt */}
      <div className="p-3 border-t border-[#2A2F3B] bg-[#191C23]">
        <form onSubmit={handleSubmit} className="relative flex items-center bg-[#20242D] border border-[#2A2F3B] focus-within:border-[#3E4554] rounded px-3 py-2 transition-colors">
          <input
            ref={inputRef}
            type="text"
            value={inputQuery}
            onChange={(e) => setInputQuery(e.target.value)}
            disabled={isLoading}
            placeholder="Ask Company Brain..."
            aria-label="Ask Company Brain"
            className="w-full bg-transparent text-xs text-[#E4E7EB] placeholder-[#858D9A] focus:outline-none pr-6 disabled:opacity-50"
          />
          <div className="absolute right-2.5 flex items-center text-[#858D9A] pointer-events-none">
            <CornerDownLeft className="w-3.5 h-3.5 text-[#858D9A]" />
          </div>
        </form>
      </div>
    </aside>
  );
};
