'use client';

import React, { useState } from 'react';
import { TimelineItem, PendingProposal, TurnState, GraphNode, EvidenceItem } from '@/types';
import { ErrorConflictPayload } from '@/lib/api';
import { 
  Check, 
  Copy, 
  ExternalLink, 
  Hash, 
  RefreshCw, 
  X, 
  FileText, 
  Loader2,
  AlertTriangle,
  GitCommit,
  Shield,
  User,
  Users,
  FolderGit2,
  Award
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
  selectedNode?: GraphNode | null;
  onClearSelectedNode?: () => void;
  onSelectEvidence?: (evidence: EvidenceItem) => void;
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
  selectedNode,
  onClearSelectedNode,
  onSelectEvidence,
}) => {
  const [copiedHash, setCopiedHash] = useState(false);
  const [copiedConflictHash, setCopiedConflictHash] = useState(false);
  const [copiedNodeId, setCopiedNodeId] = useState(false);

  const isAwaitingConfirmation = turnStatus === 'AWAITING_CONFIRMATION' && !!pendingProposal;

  const handleCopy = (text: string, setFn: (val: boolean) => void) => {
    navigator.clipboard.writeText(text);
    setFn(true);
    setTimeout(() => setFn(false), 2000);
  };

  return (
    <aside className="w-[380px] min-w-[380px] max-w-[380px] border-l border-[#2A2F3B] bg-[#191C23] flex flex-col h-[calc(100vh-3rem)] select-text relative">
      {/* Pane Top Header */}
      <div className="px-4 py-3 border-b border-[#2A2F3B] flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <GitCommit className="w-3.5 h-3.5 text-[#858D9A]" />
          <h2 className="text-xs font-semibold text-[#E4E7EB] tracking-tight">Decision Lineage & Actions</h2>
        </div>
        {isAwaitingConfirmation && (
          <span className="flex items-center gap-1.5 text-[10px] font-mono bg-[#D07D38]/10 text-[#D07D38] px-2 py-0.5 rounded border border-[#D07D38]/30">
            <span className="w-1.5 h-1.5 rounded-full bg-[#D07D38] animate-pulse" />
            Diff Staged
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* HTTP 409 Conflict Banner: Inline notice with an ochre border (#D07D38) */}
        {conflictError && (
          <div className="rounded border border-[#D07D38] bg-[#20242D] p-3 space-y-2.5 animate-in fade-in duration-200">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2 text-[#D07D38] text-xs font-semibold">
                <AlertTriangle className="w-4 h-4 text-[#D07D38] shrink-0" />
                <span className="leading-snug">Snapshot Drift Detected: Database state modified concurrently</span>
                <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-[#D07D38]/20 text-[#E4E7EB] border border-[#D07D38]/40 shrink-0">
                  HTTP 409
                </span>
              </div>
              <button
                onClick={onDismissConflict}
                className="text-[#949BA6] hover:text-[#E4E7EB] shrink-0 ml-1"
                title="Dismiss"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            <p className="text-[11px] text-[#949BA6] leading-relaxed">
              {conflictError.message || 'Target entity updated timestamp shifted in FalkorDB while proposal was staged. Mutation aborted by state machine.'}
            </p>

            {/* Hash Comparison */}
            <div className="space-y-1 font-mono text-[10px]">
              <div className="bg-[#191C23] p-1.5 rounded border border-[#2A2F3B] text-[#949BA6] flex items-center justify-between">
                <span>Stale Hash:</span>
                <span className="text-[#B84A39] truncate max-w-[180px]">
                  {conflictError.sent_hash || pendingProposal?.snapshot_hash || 'sha256:...'}
                </span>
              </div>
              <div className="bg-[#191C23] p-1.5 rounded border border-[#2A2F3B] text-[#949BA6] flex items-center justify-between">
                <span className="text-[#4E9F76]">Live Hash:</span>
                <span className="text-[#E4E7EB] truncate max-w-[180px]">
                  {conflictError.current_snapshot_hash}
                </span>
              </div>
            </div>

            {/* Re-sync Action Button */}
            <div className="flex items-center gap-2 pt-1">
              {onRefreshProposal && (
                <button
                  type="button"
                  onClick={onRefreshProposal}
                  className="flex-1 flex items-center justify-center gap-1.5 py-1 px-3 rounded text-xs font-medium bg-[#D07D38]/20 hover:bg-[#D07D38]/30 text-[#E4E7EB] border border-[#D07D38] transition-colors"
                >
                  <RefreshCw className="w-3 h-3 text-[#D07D38]" />
                  <span>Re-sync</span>
                </button>
              )}
              <button
                type="button"
                onClick={onDismissConflict}
                className="px-2.5 py-1 text-xs text-[#949BA6] hover:text-[#E4E7EB] bg-[#191C23] rounded border border-[#2A2F3B] transition-colors"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}

        {/* Selected Node Details Card Overlay */}
        {selectedNode && (
          <div className="rounded border border-[#2A2F3B] bg-[#20242D] p-3 space-y-2.5 animate-in fade-in duration-150">
            <div className="flex items-center justify-between pb-1.5 border-b border-[#2A2F3B]">
              <div className="flex items-center gap-2">
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: selectedNode.color }}
                />
                <span className="text-[10px] font-mono uppercase tracking-wider text-[#949BA6] font-semibold">
                  {selectedNode.label} Inspector
                </span>
              </div>
              {onClearSelectedNode && (
                <button
                  onClick={onClearSelectedNode}
                  className="text-[#949BA6] hover:text-[#E4E7EB]"
                  title="Close"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            <div>
              <h3 className="text-xs font-semibold text-[#E4E7EB]">{selectedNode.name}</h3>
              <div className="flex items-center justify-between text-[10px] font-mono text-[#858D9A] mt-0.5">
                <span className="truncate max-w-[210px]">{selectedNode.id}</span>
                <button
                  onClick={() => handleCopy(selectedNode.id, setCopiedNodeId)}
                  className="text-[#949BA6] hover:text-[#E4E7EB] flex items-center gap-0.5"
                >
                  {copiedNodeId ? <Check className="w-2.5 h-2.5 text-[#4E9F76]" /> : <Copy className="w-2.5 h-2.5" />}
                  <span>{copiedNodeId ? 'Copied' : 'Copy'}</span>
                </button>
              </div>
            </div>

            {selectedNode.label === 'System' ? (
              <div className="space-y-3 pt-1">
                {/* 1. Formal Accountability (Who Owns What) */}
                <div className="bg-[#191C23] border border-[#2A2F3B] rounded p-2.5 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-mono uppercase tracking-wider text-[#4E9F76] font-semibold flex items-center gap-1.5">
                      <Shield className="w-3 h-3 text-[#4E9F76]" />
                      Formal Accountability (Who Owns What)
                    </span>
                    <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-[#4E9F76]/15 text-[#4E9F76] border border-[#4E9F76]/30">
                      ACTIVE OWNS
                    </span>
                  </div>
                  <div className="space-y-1.5 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="text-[#858D9A] text-[11px]">Active Owner:</span>
                      <span className="text-[#E4E7EB] font-medium text-[11px]">{selectedNode.properties?.active_owner || 'Priya Nair (priya@acme.com)'}</span>
                    </div>
                    {selectedNode.properties?.team && (
                      <div className="flex items-center justify-between">
                        <span className="text-[#858D9A] text-[11px]">Responsible Team:</span>
                        <span className="inline-flex items-center gap-1 text-[10px] bg-[#20242D] border border-[#2A2F3B] px-1.5 py-0.2 rounded text-[#949BA6]">
                          <Users className="w-2.5 h-2.5 text-[#949BA6]" />
                          {selectedNode.properties.team}
                        </span>
                      </div>
                    )}
                    {selectedNode.properties?.project && (
                      <div className="flex items-center justify-between">
                        <span className="text-[#858D9A] text-[11px]">Active Project:</span>
                        <span className="inline-flex items-center gap-1 text-[10px] bg-[#20242D] border border-[#2A2F3B] px-1.5 py-0.2 rounded text-[#858D9A]">
                          <FolderGit2 className="w-2.5 h-2.5 text-[#858D9A]" />
                          {selectedNode.properties.project}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                {/* 2. Subject Matter Experts (Who Knows What) */}
                <div className="bg-[#191C23] border border-[#2A2F3B] rounded p-2.5 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-mono uppercase tracking-wider text-[#5E60CE] font-semibold flex items-center gap-1.5">
                      <Award className="w-3 h-3 text-[#5E60CE]" />
                      Subject Matter Experts (Who Knows What)
                    </span>
                    <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-[#5E60CE]/15 text-[#5E60CE] border border-[#5E60CE]/30">
                      COMPUTED SME
                    </span>
                  </div>

                  <div className="space-y-1.5">
                    {Array.isArray(selectedNode.properties?.sme_experts) && selectedNode.properties.sme_experts.length > 0 ? (
                      selectedNode.properties.sme_experts.map((exp: any, i: number) => (
                        <div key={i} className="bg-[#20242D] border border-[#2A2F3B] rounded p-2 text-[11px] space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-[#E4E7EB]">{exp.name}</span>
                            <span className="text-[9px] font-mono font-bold px-1.5 py-0.2 rounded bg-[#5E60CE]/20 text-[#E4E7EB] border border-[#5E60CE]/40">
                              Score: {exp.knowledge_score}
                            </span>
                          </div>
                          <div className="text-[10px] font-mono text-[#858D9A] truncate">{exp.email}</div>
                          <div className="flex items-center gap-1 text-[9px] text-[#949BA6]">
                            <span>{exp.decisions_led} decisions led</span>
                            <span>•</span>
                            <span>{exp.artifacts_authored} artifacts authored ({exp.artifact_types?.join(', ') || 'artifacts'})</span>
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="text-[11px] text-[#949BA6] italic p-1">
                        Ranked SMEs computed dynamically from authored chats, tickets, and decisions.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ) : selectedNode.properties ? (
              <div className="bg-[#191C23] border border-[#2A2F3B] rounded p-2 space-y-1 font-mono text-[10px]">
                {Object.entries(selectedNode.properties)
                  .filter(([k]) => k !== 'sme_experts')
                  .map(([k, v]) => (
                    <div key={k} className="flex flex-col pb-1 border-b border-[#2A2F3B] last:border-none last:pb-0">
                      <span className="text-[#858D9A] uppercase text-[9px] font-sans">{k.replace(/_/g, ' ')}:</span>
                      <span className="text-[#E4E7EB] break-words leading-tight mt-0.5">{String(v)}</span>
                    </div>
                  ))}
              </div>
            ) : null}

            {selectedNode.label === 'Evidence' && onSelectEvidence && selectedNode.properties && (
              <button
                type="button"
                onClick={() => onSelectEvidence({
                  id: selectedNode.id,
                  record_id: selectedNode.properties?.record_id || selectedNode.id,
                  excerpt: selectedNode.properties?.excerpt || selectedNode.name,
                  source_uri: selectedNode.properties?.source_uri || 'falkordb://evidence/' + selectedNode.id,
                  source_timestamp: selectedNode.properties?.source_timestamp || '2026-09-22T14:30:00Z',
                  content_hash: selectedNode.properties?.content_hash || 'sha256:...',
                })}
                className="w-full flex items-center justify-center gap-1.5 py-1 px-2.5 rounded text-xs font-medium bg-[#5E60CE]/15 hover:bg-[#5E60CE]/25 text-[#E4E7EB] border border-[#5E60CE]/40 transition-colors"
              >
                <FileText className="w-3 h-3 text-[#5E60CE]" />
                <span>Open Evidence Drawer</span>
              </button>
            )}
          </div>
        )}

        {/* Proposal Diff Drawer (Visible when AWAITING_CONFIRMATION) */}
        {isAwaitingConfirmation && pendingProposal && (
          <div className="rounded border border-[#2A2F3B] bg-[#20242D] p-3.5 space-y-3 animate-in fade-in duration-200">
            <div className="flex items-center justify-between pb-2 border-b border-[#2A2F3B]">
              <span className="text-xs font-semibold text-[#E4E7EB]">
                Mutation Proposal
              </span>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-[#D07D38]/10 text-[#D07D38] border border-[#D07D38]/30">
                AWAITING_CONFIRMATION
              </span>
            </div>

            {/* Target and Action metadata */}
            <div className="flex items-center justify-between text-[11px] text-[#949BA6] font-mono">
              <span>Target: <span className="text-[#4C78A8] font-semibold">{pendingProposal.action.system_name || 'payment-gateway'}</span></span>
              <span className="text-[10px] text-[#858D9A]">{pendingProposal.action.type}</span>
            </div>

            {/* Calculated Metrics Bar (Divergence Hops, Staleness Days, Risk Badge) */}
            {(() => {
              const hops = pendingProposal.calculated_metrics?.divergence_hops ?? pendingProposal.action?.calculated_metrics?.divergence_hops ?? (pendingProposal.action?.type === 'documentation_drift_fix' ? 1 : 0);
              const days = pendingProposal.calculated_metrics?.drift_staleness_days ?? pendingProposal.action?.calculated_metrics?.drift_staleness_days ?? (pendingProposal.action?.type === 'documentation_drift_fix' ? 62 : 0);
              const risk = pendingProposal.calculated_metrics?.blast_radius_risk ?? pendingProposal.action?.calculated_metrics?.blast_radius_risk ?? 'LOW';
              const downstream = pendingProposal.calculated_metrics?.affected_downstream_count ?? pendingProposal.action?.calculated_metrics?.affected_downstream_count ?? 0;

              return (
                <div className="space-y-2">
                  <div className="grid grid-cols-3 gap-2 bg-[#191C23] border border-[#2A2F3B] rounded p-2 text-center font-mono">
                    <div className="flex flex-col">
                      <span className="text-[9px] uppercase tracking-wider text-[#858D9A]">Divergence</span>
                      <span className="text-xs font-semibold text-[#E4E7EB]">{hops} hop{hops === 1 ? '' : 's'}</span>
                    </div>
                    <div className="flex flex-col border-x border-[#2A2F3B]">
                      <span className="text-[9px] uppercase tracking-wider text-[#858D9A]">Staleness</span>
                      <span className="text-xs font-semibold text-[#D07D38]">{days}d</span>
                    </div>
                    <div className="flex flex-col">
                      <span className="text-[9px] uppercase tracking-wider text-[#858D9A]">Blast Risk</span>
                      <span className={`text-[11px] font-semibold ${
                        risk === 'CRITICAL' ? 'text-[#B84A39]' : risk === 'MODERATE' ? 'text-[#D07D38]' : 'text-[#4E9F76]'
                      }`}>
                        {risk} ({downstream})
                      </span>
                    </div>
                  </div>

                  {(pendingProposal.summary || pendingProposal.action?.summary) && (
                    <div className="text-[11px] text-[#949BA6] leading-relaxed bg-[#191C23] p-2 rounded border border-[#2A2F3B]">
                      <p className="text-[#E4E7EB] font-medium mb-1">{pendingProposal.summary || pendingProposal.action.summary}</p>
                      {(pendingProposal.rationale || pendingProposal.action?.rationale) && (
                        <p className="text-[10px] text-[#858D9A]">{pendingProposal.rationale || pendingProposal.action.rationale}</p>
                      )}
                    </div>
                  )}
                </div>
              );
            })()}

            {/* Structured Diff View */}
            <div className="bg-[#191C23] border border-[#2A2F3B] rounded p-2.5 font-mono text-[11px] space-y-1.5">
              <div className="text-[10px] font-mono text-[#858D9A] pb-1 border-b border-[#2A2F3B] flex items-center justify-between">
                <span>GRAPH MUTATION DIFF</span>
                <span>FalkorDB</span>
              </div>

              {pendingProposal.action.type === 'documentation_drift_fix' || pendingProposal.proposed_action?.action_type === 'MARK_DOCUMENT_ALIGNED' ? (
                <div className="space-y-1">
                  {/* - Document status */}
                  <div className="flex items-center gap-1.5 text-[#B84A39] bg-[#B84A39]/10 px-2 py-0.5 rounded border border-[#B84A39]/20">
                    <span className="font-bold select-none">-</span>
                    <span>Document status: {pendingProposal.proposed_action?.old_value || 'stale'}</span>
                  </div>
                  {/* + Document status: updated */}
                  <div className="flex items-center gap-1.5 text-[#4E9F76] bg-[#4E9F76]/10 px-2 py-0.5 rounded border border-[#4E9F76]/20">
                    <span className="font-bold select-none">+</span>
                    <span>Document status: updated</span>
                  </div>
                  {/* + Relationship: [:ALIGNED_WITH] -> target decision */}
                  <div className="flex items-center gap-1.5 text-[#4E9F76] bg-[#4E9F76]/10 px-2 py-0.5 rounded border border-[#4E9F76]/20">
                    <span className="font-bold select-none">+</span>
                    <span>Relationship: [:ALIGNED_WITH] -&gt; {pendingProposal.proposed_action?.new_value || pendingProposal.action.superseding_decision_id || 'active_decision'}</span>
                  </div>
                </div>
              ) : pendingProposal.action.type === 'reassign_owner' || pendingProposal.proposed_action?.action_type === 'REASSIGN_OWNERSHIP' ? (
                <div className="space-y-1">
                  {/* - Current owner */}
                  <div className="flex items-center gap-1.5 text-[#B84A39] bg-[#B84A39]/10 px-2 py-0.5 rounded border border-[#B84A39]/20">
                    <span className="font-bold select-none">-</span>
                    <span>Owner: {pendingProposal.proposed_action?.old_value || pendingProposal.action.current_owner_email || 'previous_owner'}</span>
                  </div>
                  {/* + New owner */}
                  <div className="flex items-center gap-1.5 text-[#4E9F76] bg-[#4E9F76]/10 px-2 py-0.5 rounded border border-[#4E9F76]/20">
                    <span className="font-bold select-none">+</span>
                    <span>Owner: {pendingProposal.proposed_action?.new_value || pendingProposal.action.new_owner_email} (linked to System)</span>
                  </div>
                </div>
              ) : (
                <div className="space-y-1 text-[#E4E7EB]">
                  <div className="flex items-center gap-1.5 text-[#B84A39] bg-[#B84A39]/10 px-2 py-0.5 rounded">
                    <span>- {pendingProposal.action.document_id || 'entity'}: stale</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-[#4E9F76] bg-[#4E9F76]/10 px-2 py-0.5 rounded">
                    <span>+ {pendingProposal.action.superseding_decision_id || 'decision'}: linked</span>
                  </div>
                </div>
              )}
            </div>

            {/* Snapshot Hash Monospace Card */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-[10px] font-mono text-[#858D9A]">
                <span className="flex items-center gap-1">
                  <Hash className="w-3 h-3 text-[#858D9A]" />
                  Snapshot Fence Hash:
                </span>
                <button
                  onClick={() => handleCopy(pendingProposal.snapshot_hash, setCopiedHash)}
                  className="text-[#949BA6] hover:text-[#E4E7EB] flex items-center gap-1"
                >
                  {copiedHash ? <Check className="w-2.5 h-2.5 text-[#4E9F76]" /> : <Copy className="w-2.5 h-2.5" />}
                  <span>{copiedHash ? 'Copied' : 'Copy'}</span>
                </button>
              </div>
              <p className="font-mono text-[10px] text-[#858D9A] truncate bg-[#191C23] p-1.5 rounded border border-[#2A2F3B] select-all">
                {pendingProposal.snapshot_hash}
              </p>
            </div>

            {/* Action button: Apply Architecture Update */}
            <button
              type="button"
              disabled={isConfirming}
              onClick={() => onConfirmProposal(pendingProposal.proposal_id, pendingProposal.snapshot_hash)}
              className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded text-xs font-semibold bg-[#4E9F76] hover:bg-[#438B67] text-white transition-colors cursor-pointer active:scale-[0.99] disabled:opacity-50"
            >
              {isConfirming ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Applying Architecture Update...</span>
                </>
              ) : (
                <span>Apply Architecture Update</span>
              )}
            </button>
          </div>
        )}

        {/* Lineage Timeline: Git-style Vertical Commit Track */}
        <div className="space-y-3">
          <div className="flex items-center justify-between pb-1 border-b border-[#2A2F3B]">
            <span className="text-[11px] font-mono uppercase tracking-wider text-[#858D9A] font-semibold">
              Lineage Timeline
            </span>
            <span className="text-[10px] font-mono text-[#858D9A]">Commit Track</span>
          </div>

          <div className="relative pl-5 space-y-4 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-px before:bg-[#2A2F3B]">
            {timeline.map((item) => {
              const isActive = item.type === 'active' || item.status === 'active';
              const isSuperseded = item.type === 'superseded' || item.status === 'superseded';
              const isStaleOrRFC = item.type === 'rfc' || item.status === 'stale';

              // Dot colors:
              // RFC Proposal: Clay/Ochre dot (#D07D38)
              // OAuth Introspection: Ash Gray dot (#68707E)
              // Ed25519 Local Verification: Sage Green dot (#4E9F76)
              const dotColor = isActive ? '#4E9F76' : isSuperseded ? '#68707E' : '#D07D38';

              return (
                <div key={item.id} className="relative group">
                  {/* Git-style Commit Dot */}
                  <div
                    className="absolute -left-[17px] top-1.5 w-2.5 h-2.5 rounded-full border bg-[#191C23] transition-transform"
                    style={{ borderColor: dotColor, backgroundColor: dotColor }}
                  />

                  {/* Commit Log Card */}
                  <div className="bg-[#20242D] border border-[#2A2F3B] rounded p-2.5 text-xs space-y-1.5 hover:border-[#3E4554] transition-colors">
                    {/* Header with status badge */}
                    <div className="flex items-start justify-between gap-1.5">
                      <h4 className="font-semibold text-[#E4E7EB] text-xs leading-snug">
                        {item.title}
                      </h4>
                      <span
                        className={`text-[9px] font-mono font-medium px-1.5 py-0.2 rounded shrink-0 ${
                          isActive
                            ? 'bg-[#4E9F76]/10 text-[#4E9F76] border border-[#4E9F76]/30'
                            : isSuperseded
                            ? 'bg-[#68707E]/10 text-[#68707E] line-through border border-[#68707E]/30'
                            : 'bg-[#D07D38]/10 text-[#D07D38] border border-[#D07D38]/30'
                        }`}
                      >
                        {isActive ? 'active' : isSuperseded ? 'superseded' : 'stale'}
                      </span>
                    </div>

                    {/* Commit Metadata */}
                    <div className="flex items-center gap-1.5 text-[10px] font-mono text-[#858D9A]">
                      <span>{item.timestamp}</span>
                      <span>•</span>
                      <span className="text-[#949BA6]">{item.system}</span>
                      {item.author && (
                        <>
                          <span>•</span>
                          <span className="truncate max-w-[90px]">{item.author}</span>
                        </>
                      )}
                    </div>

                    {/* Summary */}
                    <p className="text-[11px] text-[#949BA6] leading-relaxed">
                      {item.summary}
                    </p>

                    {/* Evidence Footnote Link */}
                    {item.evidence_id && onSelectEvidenceId && (
                      <div className="pt-1 border-t border-[#2A2F3B] flex justify-end">
                        <button
                          type="button"
                          onClick={() => onSelectEvidenceId(item.evidence_id!)}
                          className="inline-flex items-center gap-1 text-[10px] font-mono text-[#5E60CE] hover:text-[#E4E7EB] transition-colors"
                        >
                          <span>Evidence [{item.evidence_id.slice(-6)}]</span>
                          <ExternalLink className="w-2.5 h-2.5" />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </aside>
  );
};
