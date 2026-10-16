import { GraphLink, GraphNode, TimelineItem, TurnState } from '@/types';

export const INITIAL_GRAPH_NODES: GraphNode[] = [
  {
    id: 'sys_payment_gw',
    name: 'payment-gateway',
    label: 'System',
    color: '#10b981', // emerald
    val: 24,
    properties: {
      type: 'Core Payment Ingress Service',
      sla: '99.99%',
      active_owner: 'Priya Nair',
      runtime: 'Go / gRPC',
    },
  },
  {
    id: 'usr_018f_priya',
    name: 'Priya Nair',
    label: 'Person',
    color: '#3b82f6', // blue
    val: 18,
    properties: {
      title: 'Staff Security Engineer',
      team: 'Core Payments',
      email: 'priya@acme.dev',
    },
  },
  {
    id: 'usr_018f_aarav',
    name: 'Aarav Sharma',
    label: 'Person',
    color: '#3b82f6', // blue
    val: 16,
    properties: {
      title: 'Senior Infra Engineer',
      team: 'Nexus Infra',
      email: 'aarav@acme.dev',
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
      uri: 'confluence://wiki.acme.dev/pages/payments-auth-v1',
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
      decided_at: '2026-08-15',
      rationale: 'Centralized OAuth introspection caused 180ms p99 latency spikes during gateway peaks.',
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
      decided_at: '2026-09-22',
      rationale: 'Switching to local asymmetric Ed25519 key verification dropped gateway p99 auth latency to 1.2ms.',
    },
  },
  {
    id: 'evi_018f_latency_auth',
    name: 'Slack #inc-payments (p1726000000)',
    label: 'Evidence',
    color: '#eab308', // yellow
    val: 14,
    properties: {
      excerpt: 'switching payment-gateway token validation to local Ed25519 public key verification to eliminate auth latency bottleneck.',
      source_uri: 'slack://channels/inc-payments/p1726000000',
      source_timestamp: '2026-09-22T14:30:00Z',
      content_hash: 'sha256:7f9b8c6a5d4e3f2b1a0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a',
    },
  },
  {
    id: 'evi_018f_rfc_proposal',
    name: 'Confluence RFC Excerpt',
    label: 'Evidence',
    color: '#eab308', // yellow
    val: 14,
    properties: {
      excerpt: 'RFC originally mandated network introspection per incoming HTTP request; later invalidated by benchmark incident #842.',
      source_uri: 'confluence://wiki.acme.dev/pages/payments-auth-v1#section-3',
      source_timestamp: '2026-08-10T11:00:00Z',
      content_hash: 'sha256:1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b',
    },
  },
];

export const INITIAL_GRAPH_LINKS: GraphLink[] = [
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
    source: 'dec_oauth_introspection',
    target: 'evi_018f_rfc_proposal',
    label: 'SUPPORTED_BY',
    type: 'SUPPORTED_BY',
    color: '#eab308', // solid gold
  },
];

export const TIMELINE_DATA: TimelineItem[] = [
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
    summary: 'Implemented centralized authorization check. Later identified as cause of p99 latency regressions >180ms.',
    status: 'Superseded',
    evidence_id: 'evi_018f_rfc_proposal',
  },
  {
    id: 'tl_3',
    title: 'Local Ed25519 Token Validation (Active)',
    type: 'active',
    system: 'payment-gateway',
    timestamp: 'Sep 22, 2026',
    author: 'Priya Nair & Core Payments',
    summary: 'Superseded centralized auth with in-process cryptographic verification using rotated Ed25519 public keys. Latency reduced to 1.2ms.',
    status: 'Operational / Validated',
    evidence_id: 'evi_018f_latency_auth',
  },
];

// Presets for the Demo Buttons
export const DEMO_PRESETS = {
  paymentAuthHistory: {
    query: 'Why was the payment-gateway authentication decision changed and what is the current active policy?',
    answer: {
      summary: 'The payment-gateway authorization policy was transitioned from remote OAuth introspection to in-process Ed25519 signature verification.',
      statements: [
        {
          claim: 'Payment gateway auth was migrated from OAuth network introspection to local Ed25519 asymmetric verification to eliminate latency spikes.',
          cited_evidence_ids: ['evi_018f_latency_auth'],
        },
        {
          claim: 'The original RFC mandated centralized introspection per HTTP request, which caused p99 tail latency violations under load.',
          cited_evidence_ids: ['evi_018f_rfc_proposal'],
        },
      ],
    },
    status: 'COMPLETED' as const,
    epoch: 1,
  },
  documentationDrift: {
    query: 'Check documentation drift on payment-gateway architecture RFCs and propose reconciliation.',
    answer: {
      summary: 'Documentation drift detected: "Payments Auth RFC v1" is still marked active but references the superseded OAuth introspection decision.',
      statements: [
        {
          claim: 'Payments Auth RFC v1 currently states network token introspection is mandatory, conflicting with active decision dec_ed25519_local.',
          cited_evidence_ids: ['evi_018f_rfc_proposal', 'evi_018f_latency_auth'],
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
        description: 'Update Document "Payments Auth RFC v1" status to "updated" and link ALIGNED_WITH to active Decision "Local Ed25519 Token Validation".',
      },
    },
  },
  staleSnapshotError: {
    error: 'snapshot_mismatch',
    current_snapshot_hash: 'sha256:9999999999999999999999999999999999999999999999999999999999999999',
    epoch: 3,
    message: 'Snapshot state drifted since proposal was created. Target entity updated_at values changed in FalkorDB.',
  },
};
