'use client';

import React, { useState } from 'react';
import { TimelineItem, PendingProposal, TurnState } from '@/types';
import { ErrorConflictPayload } from '@/lib/api';
import { 
  GitCommit, 
  GitPullRequest, 
  CheckCircle, 
  AlertTriangle, 
  ShieldAlert, 
  ArrowRight, 
  Clock, 
  ExternalLink, 
  Hash, 
  FileCheck2, 
  RefreshCw, 
  X, 
  Check, 
  Copy,
  Layers,
  FileCode,
  ShieldCheck,
  AlertOctagon,
  Loader2
} from 'lucide-react';

interface RightPaneProps {
  timeline: TimelineItem[];
  pendingProposal: PendingProposal | null;
  turnStatus: TurnState['status'];
  isConfirming: boolean;
  onConfirmProposal: (proposalId: string, snapshotHash: string) => Promise<void> | void;
  onSelectEvidenceId?: (evidenceId: string) => void;
  conflictError: ErrorConflictPayload | null;
  onDismissConflict: () => void;
  onRefreshProposal?: () => void;
}

export const RightPane: React.FC<RightPaneProps> = ({
  timeline,
  pendingProposal,
  turnStatus,
  isConfirming,
  onConfirmProposal,
  onSelectEvidenceId,
  conflictError,
  onDismissConflict,
  onRefreshProposal,
}) => {
  const [copiedHash, setCopiedHash] = useState(false);
  const [copiedConflictHash, setCopiedConflictHash] = useState(false);

  const isAwaitingConfirmation = turnStatus === 'AWAITING_CONFIRMATION' && !!pendingProposal;

  const handleCopy = (text: string, setFn: (val: boolean) => void) => {
    navigator.clipboard.writeText(text);
    setFn(true);
    setTimeout(() => setFn(false), 2000);
  };

  return (
    <aside className="w-[360px] min-w-[360px] max-w-[360px] border-l border-slate-800 bg-slate-950 flex flex-col h-[calc(100vh-3.5rem)] select-text relative">
      {/* Pane Header */}
      <div className="p-3.5 border-b border-slate-800/80 bg-slate-900/40 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded bg-violet-500/10 text-violet-400 border border-violet-500/20 flex items-center justify-center">
            <GitPullRequest className="w-3.5 h-3.5" />
          </div>
          <div>
            <h2 className="text-xs font-semibold text-white tracking-tight">Timeline & Proposals</h2>
            <p className="text-[10px] text-slate-400">Architectural provenance & state mutations</p>
          </div>
        </div>
        {isAwaitingConfirmation && (
          <span className="flex items-center gap-1 text-[10px] font-mono bg-amber-500/15 text-amber-300 px-2 py-0.5 rounded border border-amber-500/30 animate-pulse">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
            Action Required
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {/* Proposal Confirmation Card (visible when status is AWAITING_CONFIRMATION) */}
        {isAwaitingConfirmation && pendingProposal && (
          <div className="rounded-xl border border-amber-500/40 bg-gradient-to-b from-amber-950/30 via-slate-900 to-slate-900/90 p-4 shadow-xl shadow-amber-950/20 space-y-3.5 animate-in slide-in-from-top-2 duration-300">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-xs font-semibold text-amber-300">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                Pending Proposal Staged
              </span>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-200 border border-amber-500/30">
                2PC Lock Held
              </span>
            </div>

            {/* Target & Action Diff */}
            <div className="bg-slate-950/80 border border-slate-800 rounded-lg p-3 space-y-2 text-xs">
              <div className="flex items-center justify-between text-[11px] pb-1.5 border-b border-slate-800">
                <span className="text-slate-400">Target System:</span>
                <span className="font-mono text-emerald-400 font-medium">
                  {pendingProposal.action.system_name || 'payment-gateway'}
                </span>
              </div>
              <div className="flex items-center justify-between text-[11px] pb-1.5 border-b border-slate-800">
                <span className="text-slate-400">Action Type:</span>
                <span className="font-mono text-indigo-300">
                  {pendingProposal.action.type}
                </span>
              </div>

              {/* Specific Action Diff Details */}
              <div className="space-y-1.5 pt-1">
                <span className="text-[10px] font-mono uppercase text-slate-400 block">Proposed Diff:</span>
                <div className="font-mono text-[11px] bg-slate-900 p-2.5 rounded border border-slate-800 text-slate-300 space-y-1 leading-relaxed">
                  {pendingProposal.action.document_id && (
                    <div className="flex items-center gap-1.5 text-amber-300">
                      <span className="text-slate-500">•</span>
                      <span>Target Document:</span>
                      <span className="bg-amber-950/60 px-1 py-0.2 rounded border border-amber-800/40">
                        {pendingProposal.action.document_id}
                      </span>
                    </div>
                  )}
                  {pendingProposal.action.superseding_decision_id && (
                    <div className="flex items-center gap-1.5 text-violet-300">
                      <span className="text-slate-500">•</span>
                      <span>Link Decision:</span>
                      <span className="bg-violet-950/60 px-1 py-0.2 rounded border border-violet-800/40">
                        {pendingProposal.action.superseding_decision_id}
                      </span>
                    </div>
                  )}
                  {pendingProposal.action.new_owner_email && (
                    <div className="flex items-center gap-1.5 text-blue-300">
                      <span className="text-slate-500">•</span>
                      <span>New Owner:</span>
                      <span className="bg-blue-950/60 px-1 py-0.2 rounded border border-blue-800/40">
                        {pendingProposal.action.new_owner_email}
                      </span>
                    </div>
                  )}
                  {pendingProposal.action.description && (
                    <p className="text-[10px] text-slate-400 italic pt-1 border-t border-slate-800/60">
                      {pendingProposal.action.description}
                    </p>
                  )}
                </div>
              </div>

              {/* Fencing Snapshot Hash */}
              <div className="pt-2 border-t border-slate-800">
                <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1">
                  <span className="flex items-center gap-1 font-mono">
                    <Hash className="w-3 h-3 text-indigo-400" />
                    Snapshot Fence Hash:
                  </span>
                  <button
                    onClick={() => handleCopy(pendingProposal.snapshot_hash, setCopiedHash)}
                    className="text-indigo-400 hover:text-indigo-300 flex items-center gap-1"
                  >
                    {copiedHash ? (
                      <Check className="w-3 h-3 text-emerald-400" />
                    ) : (
                      <Copy className="w-3 h-3" />
                    )}
                  </button>
                </div>
                <p className="font-mono text-[10px] text-slate-400 truncate bg-slate-900 p-1.5 rounded border border-slate-800 select-all">
                  {pendingProposal.snapshot_hash}
                </p>
              </div>
            </div>

            {/* Confirm Mutation Button */}
            <div className="pt-1">
              <button
                type="button"
                disabled={isConfirming}
                onClick={() => onConfirmProposal(pendingProposal.proposal_id, pendingProposal.snapshot_hash)}
                className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-xs font-semibold bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white shadow-md shadow-emerald-950/40 transition-all cursor-pointer active:scale-98 disabled:opacity-50"
              >
                {isConfirming ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin text-white" />
                    <span>Verifying Snapshot & Mutating...</span>
                  </>
                ) : (
                  <>
                    <FileCheck2 className="w-4 h-4" />
                    <span>Confirm Mutation (2PC Apply)</span>
                  </>
                )}
              </button>
              <p className="text-[10px] text-center text-slate-500 mt-1.5">
                Sends UUIDv7 idempotency receipt & verifies live entity timestamps
              </p>
            </div>
          </div>
        )}

        {/* When no proposal is pending */}
        {!isAwaitingConfirmation && (
          <div className="rounded-lg border border-slate-800/80 bg-slate-900/30 p-3 text-xs text-slate-400 flex items-center gap-2.5">
            <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
            <div className="text-[11px] leading-tight">
              <span className="text-slate-200 font-medium block">Graph Consistent</span>
              <span>No unconfirmed proposals staged. State is synchronised.</span>
            </div>
          </div>
        )}

        {/* Chronological Decision Timeline */}
        <div className="space-y-3">
          <div className="flex items-center justify-between pb-1 border-b border-slate-800">
            <span className="text-[11px] font-mono uppercase tracking-wider text-slate-400 flex items-center gap-1.5 font-semibold">
              <Clock className="w-3.5 h-3.5 text-indigo-400" />
              Decision Evolution
            </span>
            <span className="text-[10px] font-mono text-slate-500">RFC → Active</span>
          </div>

          <div className="relative pl-4 space-y-6 before:absolute before:left-1.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-800">
            {timeline.map((item, index) => {
              const isRFC = item.type === 'rfc';
              const isSuperseded = item.type === 'superseded';
              const isActive = item.type === 'active';

              return (
                <div key={item.id} className="relative group">
                  {/* Timeline Node Dot */}
                  <div
                    className={`absolute -left-[19px] top-1 w-3 h-3 rounded-full border-2 bg-slate-950 flex items-center justify-center transition-transform group-hover:scale-125 ${
                      isActive
                        ? 'border-emerald-500 shadow-md shadow-emerald-500/20'
                        : isSuperseded
                        ? 'border-red-500'
                        : 'border-amber-500'
                    }`}
                  >
                    <div
                      className={`w-1 h-1 rounded-full ${
                        isActive ? 'bg-emerald-400' : isSuperseded ? 'bg-red-400' : 'bg-amber-400'
                      }`}
                    />
                  </div>

                  {/* Timeline Card */}
                  <div className="bg-slate-900/70 border border-slate-800/90 rounded-lg p-3 text-xs space-y-1.5 hover:border-slate-700 transition-colors">
                    {/* Header */}
                    <div className="flex items-start justify-between gap-1">
                      <h4 className="font-semibold text-slate-200 text-xs leading-snug">
                        {item.title}
                      </h4>
                      <span
                        className={`text-[9px] font-mono font-medium px-1.5 py-0.2 rounded shrink-0 ${
                          isActive
                            ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                            : isSuperseded
                            ? 'bg-red-500/15 text-red-400 border border-red-500/30 line-through'
                            : 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                        }`}
                      >
                        {item.status || item.type.toUpperCase()}
                      </span>
                    </div>

                    {/* Metadata */}
                    <div className="flex items-center gap-2 text-[10px] font-mono text-slate-400">
                      <span>{item.timestamp}</span>
                      <span>•</span>
                      <span className="text-slate-300">{item.system}</span>
                    </div>

                    {/* Summary */}
                    <p className="text-[11px] text-slate-300 leading-relaxed font-sans">
                      {item.summary}
                    </p>

                    {/* Author & Evidence Link */}
                    <div className="flex items-center justify-between pt-1.5 border-t border-slate-800/70 text-[10px]">
                      {item.author && (
                        <span className="text-slate-400 font-mono">By: {item.author}</span>
                      )}
                      {item.evidence_id && onSelectEvidenceId && (
                        <button
                          type="button"
                          onClick={() => onSelectEvidenceId(item.evidence_id!)}
                          className="inline-flex items-center gap-1 text-amber-400 hover:text-amber-300 font-mono transition-colors"
                        >
                          <span>Evidence [{item.evidence_id.slice(-6)}]</span>
                          <ExternalLink className="w-2.5 h-2.5" />
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* 409 Conflict Modal (if snapshot has drifted) */}
      {conflictError && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-slate-900 border border-rose-500/60 rounded-xl max-w-lg w-full p-5 shadow-2xl text-slate-100 space-y-4 animate-in zoom-in-95 duration-200">
            {/* Header */}
            <div className="flex items-start justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-lg bg-rose-500/20 text-rose-400 border border-rose-500/30 flex items-center justify-center">
                  <ShieldAlert className="w-5 h-5 text-rose-400" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-rose-200 flex items-center gap-2">
                    Snapshot Drift Detected
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30">
                      HTTP 409 Conflict
                    </span>
                  </h3>
                  <p className="text-[11px] text-slate-400">Concurrent entity mutation rejected by state machine</p>
                </div>
              </div>
              <button
                onClick={onDismissConflict}
                className="text-slate-400 hover:text-white p-1 rounded-md hover:bg-slate-800 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Explanation */}
            <div className="bg-rose-950/20 border border-rose-900/40 rounded-lg p-3 text-xs text-rose-200 space-y-1.5">
              <p className="leading-relaxed">
                The target entity&apos;s updated timestamp in FalkorDB shifted while this proposal was awaiting confirmation.
                The proposal&apos;s snapshot hash is invalid. The mutation was aborted to maintain graph integrity.
              </p>
            </div>

            {/* Hash Diff Comparison */}
            <div className="space-y-2 text-xs">
              <span className="text-[11px] font-mono uppercase tracking-wider text-slate-400">
                Cryptographic Hash Comparison:
              </span>
              <div className="space-y-1.5">
                <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800 space-y-1">
                  <div className="flex items-center justify-between text-[10px] text-slate-400">
                    <span className="font-mono text-rose-400">Staged Snapshot Hash (Expected):</span>
                    <span className="text-[10px] text-rose-400/80">Stale</span>
                  </div>
                  <p className="font-mono text-[11px] text-rose-300 truncate select-all">
                    {pendingProposal?.snapshot_hash || 'sha256:4a8c9e1f2b3d4e5a6c7b8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a'}
                  </p>
                </div>

                <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800 space-y-1">
                  <div className="flex items-center justify-between text-[10px] text-slate-400">
                    <span className="font-mono text-emerald-400">Live FalkorDB Hash (Current):</span>
                    <button
                      onClick={() => handleCopy(conflictError.current_snapshot_hash, setCopiedConflictHash)}
                      className="text-indigo-400 hover:text-indigo-300 flex items-center gap-1 text-[10px]"
                    >
                      {copiedConflictHash ? (
                        <>
                          <Check className="w-3 h-3 text-emerald-400" />
                          <span className="text-emerald-400">Copied</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-3 h-3" />
                          <span>Copy Hash</span>
                        </>
                      )}
                    </button>
                  </div>
                  <p className="font-mono text-[11px] text-emerald-300 truncate select-all">
                    {conflictError.current_snapshot_hash}
                  </p>
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
              <button
                type="button"
                onClick={onDismissConflict}
                className="px-3.5 py-1.5 text-xs text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg transition-colors"
              >
                Dismiss Alert
              </button>
              {onRefreshProposal && (
                <button
                  type="button"
                  onClick={() => {
                    onDismissConflict();
                    onRefreshProposal();
                  }}
                  className="px-3.5 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 rounded-lg transition-colors flex items-center gap-1.5"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Re-evaluate Proposal</span>
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </aside>
  );
};
