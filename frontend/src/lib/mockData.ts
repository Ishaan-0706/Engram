import { GraphLink, GraphNode, TimelineItem, TurnState } from '@/types';

// ============================================================================
// ACME PAYMENTS TOPOLOGY
// ============================================================================

export const ACME_GRAPH_NODES: GraphNode[] = [
  {
    id: 'sys_payment_gw',
    name: 'payment-gateway',
    label: 'System',
    color: '#10b981', // emerald
    val: 24,
    properties: {
      type: 'Core Ingress Payment Proxy',
      sla: '99.99%',
      active_owner: 'Priya Nair (priya@acme.com)',
      runtime: 'Go / gRPC / Envoy',
    },
  },
  {
    id: 'usr_018f_priya',
    name: 'Priya Nair',
    label: 'Person',
    color: '#3b82f6', // blue
    val: 18,
    properties: {
      title: 'Payments Lead',
      team: 'Core Payments',
      canonical_email: 'priya@acme.com',
    },
  },
  {
    id: 'usr_018f_aarav',
    name: 'Aarav Sharma',
    label: 'Person',
    color: '#3b82f6', // blue
    val: 16,
    properties: {
      title: 'Staff Engineer',
      team: 'Core Payments',
      canonical_email: 'aarav@acme.com',
    },
  },
  {
    id: 'doc_auth_rfc',
    name: 'Payments Auth RFC v1',
    label: 'Document',
    color: '#f59e0b', // amber
    val: 16,
    properties: {
      status: 'stale',
      last_reviewed: '2026-08-10',
      uri: 'confluence://acme/docs/auth-rfc-v1',
    },
  },
  {
    id: 'dec_oauth_introspection',
    name: 'OAuth Token Introspection',
    label: 'Decision',
    color: '#8b5cf6', // violet
    val: 18,
    properties: {
      status: 'superseded',
      summary: 'Use centralized OAuth introspection endpoint for payment auth',
      rationale: 'Centralized OAuth introspection caused 250ms p99 latency spikes during flash sales.',
    },
  },
  {
    id: 'dec_ed25519_local',
    name: 'Local Ed25519 Token Validation',
    label: 'Decision',
    color: '#8b5cf6', // violet
    val: 22,
    properties: {
      status: 'active',
      summary: 'Verify tokens locally via Ed25519 public keys to protect p99 latency',
      rationale: 'Local asymmetric verification dropped gateway p99 auth latency to 1.2ms.',
    },
  },
  {
    id: 'evi_018f_latency_auth',
    name: 'Slack #inc-payments (p1726000000)',
    label: 'Evidence',
    color: '#eab308', // yellow
    val: 14,
    properties: {
      excerpt: 'INC-PAYMENTS Incident Retrospective: Due to 250ms p99 latency spikes on OAuth introspection during flash sales, we are switching payment-gateway token validation to local Ed25519 public keys.',
      source_uri: 'slack://channels/inc-payments/p1726000000',
      source_timestamp: '2026-09-22T14:30:00Z',
      content_hash: 'sha256:a58b09339e0839e4e39c4a4a4918e55e5b30693a1cf5937402f1a66ff5d5642d',
    },
  },
  {
    id: 'evi_018f_rfc_proposal',
    name: 'Confluence RFC Excerpt',
    label: 'Evidence',
    color: '#eab308', // yellow
    val: 14,
    properties: {
      excerpt: 'RFC originally mandated network token introspection per incoming HTTP request; later invalidated by benchmark incident #842.',
      source_uri: 'confluence://wiki.acme.dev/pages/payments-auth-v1#section-3',
      source_timestamp: '2026-08-10T11:00:00Z',
      content_hash: 'sha256:1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b',
    },
  },
];

export const ACME_GRAPH_LINKS: GraphLink[] = [
  {
    source: 'usr_018f_priya',
    target: 'sys_payment_gw',
    label: 'OWNS',
    type: 'OWNS',
    color: '#64748b',
  },
  {
    source: 'dec_ed25519_local',
    target: 'sys_payment_gw',
    label: 'AFFECTS',
    type: 'AFFECTS',
    color: '#64748b',
  },
  {
    source: 'dec_oauth_introspection',
    target: 'sys_payment_gw',
    label: 'AFFECTS',
    type: 'AFFECTS',
    color: '#64748b',
  },
  {
    source: 'dec_ed25519_local',
    target: 'dec_oauth_introspection',
    label: 'SUPERSEDES',
    type: 'SUPERSEDES',
    color: '#ef4444', // dashed red
    dashed: true,
  },
  {
    source: 'dec_ed25519_local',
    target: 'evi_018f_latency_auth',
    label: 'SUPPORTED_BY',
    type: 'SUPPORTED_BY',
    color: '#eab308', // solid gold
  },
  {
    source: 'doc_auth_rfc',
    target: 'dec_oauth_introspection',
    label: 'PROPOSED',
    type: 'PROPOSED',
    color: '#64748b',
  },
  {
    source: 'doc_auth_rfc',
    target: 'sys_payment_gw',
    label: 'DOCUMENTS',
    type: 'DOCUMENTS',
    color: '#64748b',
  },
  {
    source: 'dec_oauth_introspection',
    target: 'evi_018f_rfc_proposal',
    label: 'SUPPORTED_BY',
    type: 'SUPPORTED_BY',
    color: '#eab308', // solid gold
  },
];

export const ACME_TIMELINE: TimelineItem[] = [
  {
    id: 'tl_1',
    title: 'Payments Auth RFC v1 Proposed',
    type: 'rfc',
    system: 'payment-gateway',
    timestamp: 'Aug 10, 2026',
    author: 'Priya Nair',
    summary: 'Initial architectural specification proposing centralized OAuth network introspection on ingress requests.',
    status: 'Stale / Needs Update',
    evidence_id: 'evi_018f_rfc_proposal',
  },
  {
    id: 'tl_2',
    title: 'OAuth Token Introspection Adopted',
    type: 'superseded',
    system: 'payment-gateway',
    timestamp: 'Aug 15, 2026',
    author: 'Architecture Guild',
    summary: 'Implemented centralized authorization check. Later identified as cause of p99 latency regressions >250ms.',
    status: 'Superseded',
    evidence_id: 'evi_018f_rfc_proposal',
  },
  {
    id: 'tl_3',
    title: 'Local Ed25519 Token Validation (Active)',
    type: 'active',
    system: 'payment-gateway',
    timestamp: 'Sep 22, 2026',
    author: 'Priya Nair & Aarav Sharma',
    summary: 'Superseded centralized auth with in-process cryptographic verification using rotated Ed25519 public keys. Latency reduced to 1.2ms.',
    status: 'Operational / Validated',
    evidence_id: 'evi_018f_latency_auth',
  },
];

// ============================================================================
// NEXUS INFRA TOPOLOGY
// ============================================================================

export const NEXUS_GRAPH_NODES: GraphNode[] = [
  {
    id: 'sys_018f_kafka',
    name: 'event-stream-cluster',
    label: 'System',
    color: '#10b981', // emerald
    val: 24,
    properties: {
      type: 'Distributed Event Streaming Cluster',
      sla: '99.999%',
      active_owner: 'Elena Rostova (elena@nexus.io)',
      runtime: 'Apache Kafka / KRaft Mode',
    },
  },
  {
    id: 'usr_018f_elena',
    name: 'Elena Rostova',
    label: 'Person',
    color: '#3b82f6', // blue
    val: 18,
    properties: {
      title: 'Platform Lead',
      team: 'Nexus Platform',
      canonical_email: 'elena@nexus.io',
    },
  },
  {
    id: 'usr_018f_devin',
    name: 'Devin Vance',
    label: 'Person',
    color: '#3b82f6', // blue
    val: 16,
    properties: {
      title: 'Principal SRE',
      team: 'Nexus Platform',
      canonical_email: 'devin@nexus.io',
    },
  },
  {
    id: 'doc_018f_kafka_runbook',
    name: 'Event Bus Partitioning SOP v2',
    label: 'Document',
    color: '#f59e0b', // amber
    val: 16,
    properties: {
      status: 'stale',
      last_reviewed: '2026-07-15',
      uri: 'notion://nexus/eng/event-bus-v2',
    },
  },
  {
    id: 'dec_018f_zookeeper',
    name: 'ZooKeeper Partition Leadership',
    label: 'Decision',
    color: '#8b5cf6', // violet
    val: 18,
    properties: {
      status: 'superseded',
      summary: 'Use ZooKeeper for partition leadership and broker metadata',
      rationale: 'ZooKeeper cross-AZ consensus timeouts triggered partition leader election deadlocks.',
    },
  },
  {
    id: 'dec_018f_kraft',
    name: 'KRaft Metadata Quorum',
    label: 'Decision',
    color: '#8b5cf6', // violet
    val: 22,
    properties: {
      status: 'active',
      summary: 'Migrate to KRaft metadata quorum to remove ZK bottleneck',
      rationale: 'KRaft consensus eliminated external dependency and eliminated leader election delays.',
    },
  },
  {
    id: 'evi_018f_kraft_consensus',
    name: 'Linear ENG-4091 Incident',
    label: 'Evidence',
    color: '#eab308', // yellow
    val: 14,
    properties: {
      excerpt: 'Migrated event-stream-cluster to KRaft mode on 2026-08-14 after ZooKeeper consensus timeouts triggered cross-AZ partition deadlocks.',
      source_uri: 'linear://nexus-infra/issue/ENG-4091',
      source_timestamp: '2026-08-14T15:30:00Z',
      content_hash: 'sha256:5d4a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a',
    },
  },
];

export const NEXUS_GRAPH_LINKS: GraphLink[] = [
  {
    source: 'usr_018f_elena',
    target: 'sys_018f_kafka',
    label: 'OWNS',
    type: 'OWNS',
    color: '#64748b',
  },
  {
    source: 'dec_018f_kraft',
    target: 'sys_018f_kafka',
    label: 'AFFECTS',
    type: 'AFFECTS',
    color: '#64748b',
  },
  {
    source: 'dec_018f_zookeeper',
    target: 'sys_018f_kafka',
    label: 'AFFECTS',
    type: 'AFFECTS',
    color: '#64748b',
  },
  {
    source: 'dec_018f_kraft',
    target: 'dec_018f_zookeeper',
    label: 'SUPERSEDES',
    type: 'SUPERSEDES',
    color: '#ef4444', // dashed red
    dashed: true,
  },
  {
    source: 'dec_018f_kraft',
    target: 'evi_018f_kraft_consensus',
    label: 'SUPPORTED_BY',
    type: 'SUPPORTED_BY',
    color: '#eab308', // solid gold
  },
  {
    source: 'doc_018f_kafka_runbook',
    target: 'dec_018f_zookeeper',
    label: 'PROPOSED',
    type: 'PROPOSED',
    color: '#64748b',
  },
  {
    source: 'doc_018f_kafka_runbook',
    target: 'sys_018f_kafka',
    label: 'DOCUMENTS',
    type: 'DOCUMENTS',
    color: '#64748b',
  },
  {
    source: 'usr_018f_devin',
    target: 'dec_018f_kraft',
    label: 'ESTABLISHED',
    type: 'ESTABLISHED',
    color: '#64748b',
  },
];

export const NEXUS_TIMELINE: TimelineItem[] = [
  {
    id: 'tl_nexus_1',
    title: 'Event Bus Partitioning SOP v2 Proposed',
    type: 'rfc',
    system: 'event-stream-cluster',
    timestamp: 'Jul 15, 2026',
    author: 'Elena Rostova',
    summary: 'Initial operational standard for ZooKeeper-managed partition leadership across 3 availability zones.',
    status: 'Stale / Superseded',
    evidence_id: 'evi_018f_kraft_consensus',
  },
  {
    id: 'tl_nexus_2',
    title: 'ZooKeeper Consensus Adopted',
    type: 'superseded',
    system: 'event-stream-cluster',
    timestamp: 'Jul 20, 2026',
    author: 'Nexus Platform Guild',
    summary: 'ZooKeeper metadata consensus. Partition leader election experienced deadlocks under network partition scenarios.',
    status: 'Superseded',
    evidence_id: 'evi_018f_kraft_consensus',
  },
  {
    id: 'tl_nexus_3',
    title: 'KRaft Metadata Quorum (Active)',
    type: 'active',
    system: 'event-stream-cluster',
    timestamp: 'Aug 14, 2026',
    author: 'Devin Vance',
    summary: 'Migrated to Kafka Raft (KRaft) metadata mode, removing external ZooKeeper dependencies and eliminating cross-AZ latency.',
    status: 'Operational / Validated',
    evidence_id: 'evi_018f_kraft_consensus',
  },
];

// Defaults for initial load
export const INITIAL_GRAPH_NODES = ACME_GRAPH_NODES;
export const INITIAL_GRAPH_LINKS = ACME_GRAPH_LINKS;
export const TIMELINE_DATA = ACME_TIMELINE;

// ============================================================================
// 3 ONE-CLICK DEMO SCENARIO PRESETS
// ============================================================================

export const DEMO_PRESETS = {
  // Button 1: "Trace Payment Auth Drift"
  tracePaymentAuthDrift: {
    query: 'Why was payment gateway auth changed and is the RFC stale?',
    answer: {
      summary: 'Payment-gateway authentication transitioned from remote OAuth introspection to in-process Ed25519 signature verification due to tail latency spikes. Documentation drift is detected: "Payments Auth RFC v1" is currently marked stale.',
      statements: [
        {
          claim: 'Payment-gateway authentication was migrated from OAuth introspection to local Ed25519 signature validation to resolve 250ms p99 tail latency spikes.',
          cited_evidence_ids: ['evi_018f_latency_auth'],
        },
        {
          claim: 'Payments Auth RFC v1 currently mandates centralized network introspection, which conflicts with active decision dec_ed25519_local.',
          cited_evidence_ids: ['evi_018f_rfc_proposal'],
        },
      ],
    },
    status: 'AWAITING_CONFIRMATION' as const,
    epoch: 2,
    pending_proposal: {
      proposal_id: '018f5e1b-7d4a-7c3e-8a12-4b6d9e0f3333',
      snapshot_hash: 'sha256:4a8c9e1f2b3d4e5a6c7b8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a',
      action: {
        type: 'documentation_drift_fix',
        system_name: 'payment-gateway',
        document_id: 'doc_auth_rfc',
        superseding_decision_id: 'dec_ed25519_local',
        description: 'Reconcile Document "Payments Auth RFC v1": transition status "stale" → "updated" and establish [:ALIGNED_WITH] edge to Decision "Local Ed25519 Token Validation".',
      },
    },
  },

  // Button 2: "Reassign Ownership"
  reassignOwnership: {
    query: 'Check current ownership of payment-gateway and stage proposal to reassign owner to aarav@acme.com.',
    answer: {
      summary: 'System payment-gateway is actively owned by Priya Nair (Core Payments). Proposal staged to transfer ownership to Staff Engineer Aarav Sharma.',
      statements: [
        {
          claim: 'System payment-gateway active ownership edge belongs to Priya Nair (Payments Lead).',
          cited_evidence_ids: ['evi_018f_latency_auth'],
        },
      ],
    },
    status: 'AWAITING_CONFIRMATION' as const,
    epoch: 2,
    pending_proposal: {
      proposal_id: '018f5e1b-7d4a-7c3e-8a12-4b6d9e0f7777',
      snapshot_hash: 'sha256:7f9b8c6a5d4e3f2b1a0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a',
      action: {
        type: 'reassign_owner',
        system_name: 'payment-gateway',
        new_owner_email: 'aarav@acme.com',
        current_owner_email: 'priya@acme.com',
        description: 'Close active [:OWNS] edge from Priya Nair and create active [:OWNS] edge pointing to Aarav Sharma (valid_from: now).',
      },
    },
  },

  // Button 3: "Verify Tenant Isolation"
  verifyTenantIsolation: {
    query: 'Query event-stream-cluster architecture and KRaft consensus decisions within Acme Payments scope.',
    answer: {
      summary: 'Strict cross-tenant isolation confirmed: System "event-stream-cluster" and KRaft consensus decisions belong exclusively to "Nexus Infra". Query returned 0 leaked records or cross-tenant edges.',
      statements: [
        {
          claim: 'Acme Payments graph contains zero entities or evidence belonging to Nexus Infra platform clusters. Cross-tenant boundaries are strictly enforced via Redis Lua CAS fencing and tenant-scoped FalkorDB graphs.',
          cited_evidence_ids: ['evi_018f_latency_auth'],
        },
      ],
    },
    status: 'COMPLETED' as const,
    epoch: 2,
  },

  // Stale snapshot conflict payload for 409 simulation
  staleSnapshotConflict: {
    error: 'snapshot_mismatch',
    sent_hash: 'sha256:4a8c9e1f2b3d4e5a6c7b8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a',
    current_snapshot_hash: 'sha256:9999999999999999999999999999999999999999999999999999999999999999',
    epoch: 3,
    message: 'Snapshot state drifted in FalkorDB since proposal was staged. Concurrent entity mutation detected.',
  },
};
