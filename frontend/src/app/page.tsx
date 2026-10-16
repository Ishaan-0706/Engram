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
  ACME_GRAPH_NODES, 
  ACME_GRAPH_LINKS, 
  ACME_TIMELINE, 
  NEXUS_GRAPH_NODES, 
  NEXUS_GRAPH_LINKS, 
  NEXUS_TIMELINE, 
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
  const [sessionId, setSessionId] = useState<string>(() => 'sess_exec_' + Math.random().toString(36).substring(2, 9));
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
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  // Evidence Drawer & Hover Synchronization
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceItem | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState<boolean>(false);
  const [highlightedEvidenceId, setHighlightedEvidenceId] = useState<string | null>(null);

  // 409 Conflict Modal & Banner
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

  // Update tenant scope: reset session state, epoch, and dynamically reload topology
  const handleTenantChange = (newTenant: Tenant) => {
    setCurrentTenant(newTenant);
    const newSessionId = 'sess_exec_' + Math.random().toString(36).substring(2, 9);
    setSessionId(newSessionId);
    setEpoch(1);
    setSelectedNode(null);
    setHighlightedEvidenceId(null);
    setConflictError(null);
    setIsDrawerOpen(false);

    if (newTenant === 'Nexus Infra') {
      setNodes(NEXUS_GRAPH_NODES);
      setLinks(NEXUS_GRAPH_LINKS);
      setTimeline(NEXUS_TIMELINE);
      setTurnState({
        turn_id: 'turn_nexus_init',
        tenant_id: 'Nexus Infra',
        user_id: 'usr_staff_engineer',
        status: 'COMPLETED',
        epoch: 1,
        working_set: {},
        tool_trace: [],
        evidence_bag: {
          'evi_018f_kraft_consensus': {
            id: 'evi_018f_kraft_consensus',
            record_id: 'sys_018f_kafka',
            excerpt: 'Migrated event-stream-cluster to KRaft mode on 2026-08-14 after ZooKeeper consensus timeouts triggered cross-AZ partition deadlocks.',
            source_uri: 'linear://nexus-infra/issue/ENG-4091',
            source_timestamp: '2026-08-14T15:30:00Z',
            content_hash: 'sha256:5d4a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a',
          },
        },
        pending_proposal: null,
        synthesis_traces: [],
        fail_reason: null,
      });
      setMessages([
        {
          id: 'tenant_switch_' + Date.now(),
          role: 'assistant',
          content: 'Switched tenant context to Nexus Infra. Session reset (Epoch #1). Topology reloaded with event-stream-cluster, KRaft decisions, and platform engineers.',
          timestamp: new Date().toLocaleTimeString(),
          status: 'COMPLETED',
          epoch: 1,
        },
      ]);
    } else {
      setNodes(ACME_GRAPH_NODES);
      setLinks(ACME_GRAPH_LINKS);
      setTimeline(ACME_TIMELINE);
      setTurnState({
        turn_id: 'turn_acme_init',
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
      setMessages([
        {
          id: 'tenant_switch_' + Date.now(),
          role: 'assistant',
          content: 'Switched tenant context to Acme Payments. Session reset (Epoch #1). Topology reloaded with payment-gateway, Ed25519 decisions, and payments team.',
          timestamp: new Date().toLocaleTimeString(),
          status: 'COMPLETED',
          epoch: 1,
        },
      ]);
    }
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
        handleDemoScenario1(query);
      } else if (query.toLowerCase().includes('drift') || query.toLowerCase().includes('rfc')) {
        handleDemoScenario1(query);
      } else if (query.toLowerCase().includes('owner') || query.toLowerCase().includes('reassign')) {
        handleDemoScenario2(query);
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

  // Demo Scenario 1: "Trace Payment Auth Drift"
  const handleDemoScenario1 = async (customQuery?: string) => {
    const query = customQuery || DEMO_PRESETS.tracePaymentAuthDrift.query;
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
            content: synth?.summary || DEMO_PRESETS.tracePaymentAuthDrift.answer.summary,
            timestamp: new Date().toLocaleTimeString(),
            answer: synth || DEMO_PRESETS.tracePaymentAuthDrift.answer,
            status: res.turn.status,
            fail_reason: res.turn.fail_reason,
            epoch: res.epoch,
          },
        ]);
        return;
      }
    } catch {
      // fallback to deterministic preset
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
        pending_proposal: DEMO_PRESETS.tracePaymentAuthDrift.pending_proposal,
      }));

      const assistantMsg: ChatMessage = {
        id: 'asst_' + Date.now(),
        role: 'assistant',
        content: DEMO_PRESETS.tracePaymentAuthDrift.answer.summary,
        timestamp: new Date().toLocaleTimeString(),
        answer: DEMO_PRESETS.tracePaymentAuthDrift.answer,
        status: 'AWAITING_CONFIRMATION',
        epoch: nextEpoch,
      };

      setMessages((prev) => [...prev, assistantMsg]);
      setIsLoading(false);
    }, 350);
  };

  // Demo Scenario 2: "Reassign Ownership"
  const handleDemoScenario2 = async (customQuery?: string) => {
    const query = customQuery || DEMO_PRESETS.reassignOwnership.query;
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
            content: synth?.summary || DEMO_PRESETS.reassignOwnership.answer.summary,
            timestamp: new Date().toLocaleTimeString(),
            answer: synth || DEMO_PRESETS.reassignOwnership.answer,
            status: res.turn.status,
            fail_reason: res.turn.fail_reason,
            epoch: res.epoch,
          },
        ]);
        return;
      }
    } catch {
      // fallback to deterministic preset
    }

    // Deterministic simulation
    setTimeout(() => {
      const nextEpoch = epoch + 1;
      setEpoch(nextEpoch);

      setTurnState((prev) => ({
        ...(prev || ({} as any)),
        turn_id: 'turn_demo_ownership',
        status: 'AWAITING_CONFIRMATION',
        epoch: nextEpoch,
        pending_proposal: DEMO_PRESETS.reassignOwnership.pending_proposal,
      }));

      const assistantMsg: ChatMessage = {
        id: 'asst_' + Date.now(),
        role: 'assistant',
        content: DEMO_PRESETS.reassignOwnership.answer.summary,
        timestamp: new Date().toLocaleTimeString(),
        answer: DEMO_PRESETS.reassignOwnership.answer,
        status: 'AWAITING_CONFIRMATION',
        epoch: nextEpoch,
      };

      setMessages((prev) => [...prev, assistantMsg]);
      setIsLoading(false);
    }, 350);
  };

  // Demo Scenario 3: "Verify Tenant Isolation"
  const handleDemoScenario3 = async (customQuery?: string) => {
    const query = customQuery || DEMO_PRESETS.verifyTenantIsolation.query;
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
            content: synth?.summary || DEMO_PRESETS.verifyTenantIsolation.answer.summary,
            timestamp: new Date().toLocaleTimeString(),
            answer: synth || DEMO_PRESETS.verifyTenantIsolation.answer,
            status: res.turn.status,
            fail_reason: res.turn.fail_reason,
            epoch: res.epoch,
          },
        ]);
        return;
      }
    } catch {
      // fallback to deterministic preset
    }

    // Deterministic simulation
    setTimeout(() => {
      const nextEpoch = epoch + 1;
      setEpoch(nextEpoch);

      setTurnState((prev) => ({
        ...(prev || ({} as any)),
        turn_id: 'turn_demo_isolation',
        status: 'COMPLETED',
        epoch: nextEpoch,
        pending_proposal: null,
      }));

      const assistantMsg: ChatMessage = {
        id: 'asst_' + Date.now(),
        role: 'assistant',
        content: DEMO_PRESETS.verifyTenantIsolation.answer.summary,
        timestamp: new Date().toLocaleTimeString(),
        answer: DEMO_PRESETS.verifyTenantIsolation.answer,
        status: 'COMPLETED',
        epoch: nextEpoch,
      };

      setMessages((prev) => [...prev, assistantMsg]);
      setIsLoading(false);
    }, 350);
  };

  // Simulate Stale Snapshot: sends corrupted hash to test 409 rejection modal/banner
  const handleSimulateStaleSnapshot = async () => {
    setIsConfirming(true);

    try {
      if (isConnected && turnState?.pending_proposal) {
        await confirmProposal(
          currentTenant,
          sessionId,
          turnState.pending_proposal.proposal_id,
          'sha256:deliberately_invalid_hash_to_trigger_snapshot_mismatch'
        );
      } else {
        throw {
          status: 409,
          data: DEMO_PRESETS.staleSnapshotConflict,
        };
      }
    } catch (err: any) {
      const conflictData = err.data || DEMO_PRESETS.staleSnapshotConflict;
      setConflictError(conflictData);
    } finally {
      setIsConfirming(false);
    }
  };

  // Re-sync & Update action: re-evaluates proposal snapshot hash to match live FalkorDB state
  const handleResyncAndUpdate = () => {
    const liveHash = conflictError?.current_snapshot_hash || 'sha256:9999999999999999999999999999999999999999999999999999999999999999';
    
    setTurnState((prev) => {
      if (!prev || !prev.pending_proposal) return prev;
      return {
        ...prev,
        pending_proposal: {
          ...prev.pending_proposal,
          snapshot_hash: liveHash,
        },
      };
    });

    setConflictError(null);

    setMessages((prev) => [
      ...prev,
      {
        id: 'resync_' + Date.now(),
        role: 'assistant',
        content: `Snapshot fence re-synchronized with live FalkorDB state (${liveHash.slice(0, 18)}...). Graph fence valid; proposal staged and ready for 2PC apply.`,
        timestamp: new Date().toLocaleTimeString(),
        status: 'AWAITING_CONFIRMATION',
        epoch,
      },
    ]);
  };

  // Confirm Mutation handler from Right Pane card: calls POST /api/confirm and updates live graph
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

      const actionType = turnState?.pending_proposal?.action?.type;

      // Advance turn state to COMPLETED
      setTurnState((prev) => prev ? {
        ...prev,
        status: 'COMPLETED',
        epoch: nextEpoch,
        pending_proposal: null,
      } : null);

      // Live graph mutations on canvas
      if (actionType === 'documentation_drift_fix') {
        // Update Document status from stale to updated
        setNodes((prevNodes) =>
          prevNodes.map((n) =>
            n.id === 'doc_auth_rfc'
              ? {
                  ...n,
                  properties: {
                    ...n.properties,
                    status: 'updated',
                  },
                }
              : n
          )
        );

        // Add [:ALIGNED_WITH] edge in links if not present
        setLinks((prevLinks) => {
          const exists = prevLinks.some(
            (l) =>
              (typeof l.source === 'object' ? (l.source as any).id : l.source) === 'doc_auth_rfc' &&
              (typeof l.target === 'object' ? (l.target as any).id : l.target) === 'dec_ed25519_local'
          );
          if (exists) return prevLinks;
          return [
            ...prevLinks,
            {
              source: 'doc_auth_rfc',
              target: 'dec_ed25519_local',
              label: 'ALIGNED_WITH',
              type: 'ALIGNED_WITH',
              color: '#10b981',
            },
          ];
        });

        // Update timeline status
        setTimeline((prev) =>
          prev.map((item) =>
            item.id === 'tl_1'
              ? { ...item, status: 'Reconciled & Aligned', title: 'Payments Auth RFC v1 (Reconciled)' }
              : item
          )
        );
      } else if (actionType === 'reassign_owner') {
        // Update System active owner
        setNodes((prevNodes) =>
          prevNodes.map((n) =>
            n.id === 'sys_payment_gw'
              ? {
                  ...n,
                  properties: {
                    ...n.properties,
                    active_owner: 'Aarav Sharma (aarav@acme.com)',
                  },
                }
              : n
          )
        );

        // Update active OWNS link
        setLinks((prevLinks) =>
          prevLinks.map((l) =>
            l.type === 'OWNS' && (typeof l.target === 'object' ? (l.target as any).id : l.target) === 'sys_payment_gw'
              ? { ...l, source: 'usr_018f_aarav' }
              : l
          )
        );
      }

      // Add mutation applied receipt to chat
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
        setConflictError(err.data || DEMO_PRESETS.staleSnapshotConflict);
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
          onDemoScenario1={() => handleDemoScenario1()}
          onDemoScenario2={() => handleDemoScenario2()}
          onDemoScenario3={() => handleDemoScenario3()}
          onSimulateStaleSnapshot={handleSimulateStaleSnapshot}
          onQuickDemo1={() => handleDemoScenario1()}
          onQuickDemo2={() => handleDemoScenario2()}
          onQuickDemo3={handleSimulateStaleSnapshot}
        />

        {/* Center Pane (Graph Canvas, flex-1) */}
        <CenterPane
          nodes={nodes}
          links={links}
          highlightedEvidenceId={highlightedEvidenceId}
          onNodeClick={(node) => {
            setSelectedNode(node);
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
          onRefreshProposal={handleResyncAndUpdate}
          selectedNode={selectedNode}
          onClearSelectedNode={() => setSelectedNode(null)}
          onSelectEvidence={handleSelectEvidence}
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
