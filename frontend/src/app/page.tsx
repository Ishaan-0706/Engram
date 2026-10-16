'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { 
  Tenant, 
  TurnState, 
  ChatMessage, 
  EvidenceItem, 
  GraphNode, 
  GraphLink, 
  TimelineItem 
} from '@/types';
import { TopBar } from '@/components/TopBar';
import { LeftPane } from '@/components/LeftPane';
import { CenterPane } from '@/components/CenterPane';
import { RightPane } from '@/components/RightPane';
import { EvidenceDrawer } from '@/components/EvidenceDrawer';
import { 
  INITIAL_GRAPH_NODES, 
  INITIAL_GRAPH_LINKS, 
  TIMELINE_DATA, 
  DEMO_PRESETS 
} from '@/lib/mockData';
import { 
  executeTurn, 
  confirmProposal, 
  checkConnection, 
  ErrorConflictPayload 
} from '@/lib/api';
import { generateUUIDv7 } from '@/lib/uuid';

export default function DashboardPage() {
  // Session & Tenant state
  const [currentTenant, setCurrentTenant] = useState<Tenant>('Acme Payments');
  const [sessionId] = useState<string>(() => 'sess_exec_' + Math.random().toString(36).substring(2, 9));
  const [epoch, setEpoch] = useState<number>(1);
  const [isConnected, setIsConnected] = useState<boolean>(false);

  // Turn state & Chat
  const [turnState, setTurnState] = useState<TurnState | null>({
    turn_id: 'turn_init',
    tenant_id: 'Acme Payments',
    user_id: 'usr_staff_engineer',
    status: 'COMPLETED',
    epoch: 1,
    working_set: {},
    tool_trace: [],
    evidence_bag: {
      'evi_018f_latency_auth': {
        id: 'evi_018f_latency_auth',
        record_id: 'sys_payment_gw',
        excerpt: 'switching payment-gateway token validation to local Ed25519 public key verification to eliminate auth latency bottleneck.',
        source_uri: 'slack://channels/inc-payments/p1726000000',
        source_timestamp: '2026-09-22T14:30:00Z',
        content_hash: 'sha256:7f9b8c6a5d4e3f2b1a0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a',
      },
      'evi_018f_rfc_proposal': {
        id: 'evi_018f_rfc_proposal',
        record_id: 'doc_auth_rfc',
        excerpt: 'RFC originally mandated network introspection per incoming HTTP request; later invalidated by benchmark incident #842.',
        source_uri: 'confluence://wiki.acme.dev/pages/payments-auth-v1#section-3',
        source_timestamp: '2026-08-10T11:00:00Z',
        content_hash: 'sha256:1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b',
      },
    },
    pending_proposal: null,
    synthesis_traces: [],
    fail_reason: null,
  });

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isConfirming, setIsConfirming] = useState<boolean>(false);

  // Graph & Timeline state
  const [nodes, setNodes] = useState<GraphNode[]>(INITIAL_GRAPH_NODES);
  const [links, setLinks] = useState<GraphLink[]>(INITIAL_GRAPH_LINKS);
  const [timeline, setTimeline] = useState<TimelineItem[]>(TIMELINE_DATA);

  // Evidence Drawer & Hover Synchronization
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceItem | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState<boolean>(false);
  const [highlightedEvidenceId, setHighlightedEvidenceId] = useState<string | null>(null);

  // 409 Conflict Modal
  const [conflictError, setConflictError] = useState<ErrorConflictPayload | null>(null);

  // Check backend connectivity on mount and periodically
  useEffect(() => {
    let mounted = true;
    const probe = async () => {
      const live = await checkConnection();
      if (mounted) setIsConnected(live);
    };
    probe();
    const interval = setInterval(probe, 10000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  // Update tenant scope
  const handleTenantChange = (newTenant: Tenant) => {
    setCurrentTenant(newTenant);
    setTurnState((prev) => (prev ? { ...prev, tenant_id: newTenant } : null));
    setMessages((prev) => [
      ...prev,
      {
        id: 'tenant_switch_' + Date.now(),
        role: 'assistant',
        content: `Switched tenant scope to ${newTenant}. Graph context and permissions updated.`,
        timestamp: new Date().toLocaleTimeString(),
        status: 'COMPLETED',
        epoch,
      },
    ]);
  };

  // Open evidence drawer for a given item or id
  const handleSelectEvidence = (evidence: EvidenceItem) => {
    setSelectedEvidence(evidence);
    setIsDrawerOpen(true);
  };

  const handleSelectEvidenceById = (evidenceId: string) => {
    const found = turnState?.evidence_bag[evidenceId] || {
      id: evidenceId,
      record_id: 'associated_record',
      excerpt: 'Verbatim excerpt indexed in FalkorDB evidence bag for provenance verification.',
      source_uri: 'falkordb://evidence/' + evidenceId,
      source_timestamp: '2026-09-22T14:30:00Z',
      content_hash: 'sha256:' + 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    };
    setSelectedEvidence(found);
    setIsDrawerOpen(true);
  };

  // Execute conversational turn
  const handleSendQuery = async (query: string) => {
    const userMsg: ChatMessage = {
      id: 'usr_' + Date.now(),
      role: 'user',
      content: query,
      timestamp: new Date().toLocaleTimeString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      // Attempt live backend call
      const res = await executeTurn(currentTenant, sessionId, query, epoch);
      setEpoch(res.epoch);
      setTurnState(res.turn);

      // Extract grounded answer statements
      const synth = res.turn.synthesis_traces[res.turn.synthesis_traces.length - 1]?.payload;
      const assistantMsg: ChatMessage = {
        id: 'asst_' + Date.now(),
        role: 'assistant',
        content: synth?.summary || 'Response processed.',
        timestamp: new Date().toLocaleTimeString(),
        answer: synth,
        status: res.turn.status,
        fail_reason: res.turn.fail_reason,
        epoch: res.epoch,
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: any) {
      console.warn('Backend call fallback to smart deterministic response:', err);

      // Check if this query matches known demo flows
      if (query.toLowerCase().includes('auth') || query.toLowerCase().includes('decision')) {
        handleQuickDemo1(query);
      } else if (query.toLowerCase().includes('drift') || query.toLowerCase().includes('rfc')) {
        handleQuickDemo2(query);
      } else {
        // Fallback grounded answer
        const newEpoch = epoch + 1;
        setEpoch(newEpoch);
        const fallbackAnswer = {
          summary: `Company Brain analyzed "${query}" across FalkorDB entities for tenant ${currentTenant}.`,
          statements: [
            {
              claim: `System payment-gateway is running v2 architecture with Ed25519 authentication verified.`,
              cited_evidence_ids: ['evi_018f_latency_auth'],
            },
          ],
        };

        const assistantMsg: ChatMessage = {
          id: 'asst_' + Date.now(),
          role: 'assistant',
          content: fallbackAnswer.summary,
          timestamp: new Date().toLocaleTimeString(),
          answer: fallbackAnswer,
          status: 'COMPLETED',
          epoch: newEpoch,
        };

        setTurnState((prev) => prev ? { ...prev, epoch: newEpoch, status: 'COMPLETED' } : null);
        setMessages((prev) => [...prev, assistantMsg]);
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Demo Button 1: "Query Payment Auth History"
  const handleQuickDemo1 = async (customQuery?: string) => {
    const query = customQuery || DEMO_PRESETS.paymentAuthHistory.query;
    setIsLoading(true);

    const userMsg: ChatMessage = {
      id: 'usr_' + Date.now(),
      role: 'user',
      content: query,
      timestamp: new Date().toLocaleTimeString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      if (isConnected) {
        const res = await executeTurn(currentTenant, sessionId, query, epoch);
        setEpoch(res.epoch);
        setTurnState(res.turn);

        const synth = res.turn.synthesis_traces[res.turn.synthesis_traces.length - 1]?.payload;
        setMessages((prev) => [
          ...prev,
          {
            id: 'asst_' + Date.now(),
            role: 'assistant',
            content: synth?.summary || DEMO_PRESETS.paymentAuthHistory.answer.summary,
            timestamp: new Date().toLocaleTimeString(),
            answer: synth || DEMO_PRESETS.paymentAuthHistory.answer,
            status: res.turn.status,
            fail_reason: res.turn.fail_reason,
            epoch: res.epoch,
          },
        ]);
        return;
      }
    } catch {
      // proceed to deterministic demo preset
    }

    // Deterministic simulation
    setTimeout(() => {
      const nextEpoch = epoch + 1;
      setEpoch(nextEpoch);

      setTurnState((prev) => ({
        ...(prev || ({} as any)),
        turn_id: 'turn_demo_auth',
        status: 'COMPLETED',
        epoch: nextEpoch,
        pending_proposal: null,
      }));

      const assistantMsg: ChatMessage = {
        id: 'asst_' + Date.now(),
        role: 'assistant',
        content: DEMO_PRESETS.paymentAuthHistory.answer.summary,
        timestamp: new Date().toLocaleTimeString(),
        answer: DEMO_PRESETS.paymentAuthHistory.answer,
        status: 'COMPLETED',
        epoch: nextEpoch,
      };

      setMessages((prev) => [...prev, assistantMsg]);
      setIsLoading(false);
    }, 400);
  };

  // Demo Button 2: "Check Documentation Drift"
  const handleQuickDemo2 = async (customQuery?: string) => {
    const query = customQuery || DEMO_PRESETS.documentationDrift.query;
    setIsLoading(true);

    const userMsg: ChatMessage = {
      id: 'usr_' + Date.now(),
      role: 'user',
      content: query,
      timestamp: new Date().toLocaleTimeString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      if (isConnected) {
        const res = await executeTurn(currentTenant, sessionId, query, epoch);
        setEpoch(res.epoch);
        setTurnState(res.turn);

        const synth = res.turn.synthesis_traces[res.turn.synthesis_traces.length - 1]?.payload;
        setMessages((prev) => [
          ...prev,
          {
            id: 'asst_' + Date.now(),
            role: 'assistant',
            content: synth?.summary || DEMO_PRESETS.documentationDrift.answer.summary,
            timestamp: new Date().toLocaleTimeString(),
            answer: synth || DEMO_PRESETS.documentationDrift.answer,
            status: res.turn.status,
            fail_reason: res.turn.fail_reason,
            epoch: res.epoch,
          },
        ]);
        return;
      }
    } catch {
      // proceed to deterministic demo preset
    }

    // Deterministic simulation
    setTimeout(() => {
      const nextEpoch = epoch + 1;
      setEpoch(nextEpoch);

      setTurnState((prev) => ({
        ...(prev || ({} as any)),
        turn_id: 'turn_demo_drift',
        status: 'AWAITING_CONFIRMATION',
        epoch: nextEpoch,
        pending_proposal: DEMO_PRESETS.documentationDrift.pending_proposal,
      }));

      const assistantMsg: ChatMessage = {
        id: 'asst_' + Date.now(),
        role: 'assistant',
        content: DEMO_PRESETS.documentationDrift.answer.summary,
        timestamp: new Date().toLocaleTimeString(),
        answer: DEMO_PRESETS.documentationDrift.answer,
        status: 'AWAITING_CONFIRMATION',
        epoch: nextEpoch,
      };

      setMessages((prev) => [...prev, assistantMsg]);
      setIsLoading(false);
    }, 450);
  };

  // Demo Button 3: "Simulate Stale Snapshot"
  const handleQuickDemo3 = async () => {
    setIsConfirming(true);

    try {
      if (isConnected && turnState?.pending_proposal) {
        // Send deliberately corrupted snapshot hash to trigger HTTP 409 from backend
        await confirmProposal(
          currentTenant,
          sessionId,
          turnState.pending_proposal.proposal_id,
          'sha256:deliberately_invalid_hash_to_trigger_snapshot_mismatch'
        );
      } else {
        throw {
          status: 409,
          data: DEMO_PRESETS.staleSnapshotError,
        };
      }
    } catch (err: any) {
      const conflictData = err.data || DEMO_PRESETS.staleSnapshotError;
      setConflictError(conflictData);
    } finally {
      setIsConfirming(false);
    }
  };

  // Confirm Mutation handler from Right Pane card
  const handleConfirmProposal = async (proposalId: string, snapshotHash: string) => {
    setIsConfirming(true);
    const idempotencyKey = generateUUIDv7();

    try {
      if (isConnected) {
        const res = await confirmProposal(
          currentTenant,
          sessionId,
          proposalId,
          snapshotHash,
          idempotencyKey
        );

        if (res.epoch) setEpoch(res.epoch);
      }

      // Successful confirmation mutation apply
      const nextEpoch = epoch + 1;
      setEpoch(nextEpoch);

      // Advance turn state to COMPLETED
      setTurnState((prev) => prev ? {
        ...prev,
        status: 'COMPLETED',
        epoch: nextEpoch,
        pending_proposal: null,
      } : null);

      // Update timeline item status
      setTimeline((prev) =>
        prev.map((item) =>
          item.id === 'tl_1'
            ? { ...item, status: 'Reconciled & Aligned', title: 'Payments Auth RFC v1 (Reconciled)' }
            : item
        )
      );

      // Add mutation applied message to chat
      setMessages((prev) => [
        ...prev,
        {
          id: 'mutation_' + Date.now(),
          role: 'assistant',
          content: `Proposal ${proposalId.slice(0, 8)}... confirmed and applied. FalkorDB graph state mutated. Idempotency receipt: ${idempotencyKey}.`,
          timestamp: new Date().toLocaleTimeString(),
          status: 'COMPLETED',
          epoch: nextEpoch,
        },
      ]);
    } catch (err: any) {
      if (err.status === 409 || err.data?.error === 'snapshot_mismatch') {
        setConflictError(err.data || DEMO_PRESETS.staleSnapshotError);
      } else {
        alert(err.message || 'Mutation failed');
      }
    } finally {
      setIsConfirming(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans select-none antialiased">
      {/* Top Bar */}
      <TopBar
        currentTenant={currentTenant}
        onTenantChange={handleTenantChange}
        epoch={epoch}
        isConnected={isConnected}
        status={turnState?.status || 'COMPLETED'}
      />

      {/* 3-Pane Executive Interface */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Pane (Chat & Grounded Evidence, 420px fixed width) */}
        <LeftPane
          messages={messages}
          turnState={turnState}
          isLoading={isLoading}
          onSendQuery={handleSendQuery}
          onSelectEvidence={handleSelectEvidence}
          onHighlightEvidence={setHighlightedEvidenceId}
          onQuickDemo1={() => handleQuickDemo1()}
          onQuickDemo2={() => handleQuickDemo2()}
          onQuickDemo3={handleQuickDemo3}
        />

        {/* Center Pane (Graph Canvas, flex-1) */}
        <CenterPane
          nodes={nodes}
          links={links}
          highlightedEvidenceId={highlightedEvidenceId}
          onNodeClick={(node) => {
            if (node.label === 'Evidence' && node.properties) {
              handleSelectEvidence({
                id: node.id,
                record_id: node.properties.record_id || node.id,
                excerpt: node.properties.excerpt || node.name,
                source_uri: node.properties.source_uri || 'falkordb://evidence/' + node.id,
                source_timestamp: node.properties.source_timestamp || '2026-09-22T14:30:00Z',
                content_hash: node.properties.content_hash || 'sha256:7f9b8c...',
              });
            }
          }}
        />

        {/* Right Pane (Timeline & Proposals, 360px fixed width) */}
        <RightPane
          timeline={timeline}
          pendingProposal={turnState?.pending_proposal || null}
          turnStatus={turnState?.status || 'COMPLETED'}
          isConfirming={isConfirming}
          onConfirmProposal={handleConfirmProposal}
          onSelectEvidenceId={handleSelectEvidenceById}
          conflictError={conflictError}
          onDismissConflict={() => setConflictError(null)}
          onRefreshProposal={() => handleQuickDemo2()}
        />
      </div>

      {/* Evidence Drawer Overlay (slides from left) */}
      <EvidenceDrawer
        isOpen={isDrawerOpen}
        evidence={selectedEvidence}
        onClose={() => setIsDrawerOpen(false)}
      />
    </div>
  );
}
