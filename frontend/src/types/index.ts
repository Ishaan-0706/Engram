export type Tenant = 'Acme Payments' | 'Nexus Infra';

export type EntityLabel = 'Person' | 'System' | 'Decision' | 'Document' | 'Evidence' | 'Team' | 'Project' | 'Source';

export interface EvidenceItem {
  id: string;
  record_id: string;
  excerpt: string;
  source_uri: string;
  source_timestamp: string;
  content_hash: string;
  source_type?: string;
  author?: string;
}

export interface StatementClaim {
  claim?: string;
  text?: string;
  cited_evidence_ids: string[];
}

export interface GroundedAnswer {
  summary?: string;
  claims?: StatementClaim[];
  statements?: StatementClaim[];
}

export interface CalculatedMetrics {
  divergence_hops: number;
  drift_staleness_days: number;
  blast_radius_risk: 'LOW' | 'MODERATE' | 'CRITICAL';
  affected_downstream_count: number;
}

export interface ProposedAction {
  action_type: string;
  target_entity_id: string;
  target_field: string;
  old_value: string;
  new_value: string;
  supporting_evidence_ids: string[];
}

export interface PendingProposal {
  proposal_id: string;
  snapshot_hash: string;
  summary?: string;
  rationale?: string;
  calculated_metrics?: CalculatedMetrics;
  proposed_action?: ProposedAction;
  action: {
    type: string;
    system_name?: string;
    new_owner_email?: string;
    document_id?: string;
    superseding_decision_id?: string;
    record_ids?: string[];
    summary?: string;
    rationale?: string;
    calculated_metrics?: CalculatedMetrics;
    proposed_action?: ProposedAction;
    [key: string]: any;
  };
}

export interface TurnState {
  turn_id: string;
  tenant_id: string;
  user_id: string;
  status: 'PLANNING' | 'EXECUTING_TOOLS' | 'AWAITING_CONFIRMATION' | 'COMPLETED' | 'FAILED';
  epoch: number;
  working_set: Record<string, { label: string; properties: Record<string, any> }>;
  tool_trace: Array<{ tool: string; ok: boolean; at: string; error_code?: string }>;
  evidence_bag: Record<string, EvidenceItem>;
  pending_proposal: PendingProposal | null;
  synthesis_traces: Array<{ attempt: number; ok: boolean; payload: any }>;
  fail_reason: 'unverifiable_claim' | 'stale_fence' | 'lease_expired' | 'execute_crash' | null;
  session_id?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  answer?: GroundedAnswer;
  status?: TurnState['status'];
  fail_reason?: TurnState['fail_reason'];
  epoch?: number;
}

export interface GraphNode {
  id: string;
  name: string;
  label: EntityLabel;
  properties?: Record<string, any>;
  color: string;
  val: number;
  highlighted?: boolean;
  dimmed?: boolean;
}

export interface GraphLink {
  source: string;
  target: string;
  label: string;
  type?: 'SUPERSEDES' | 'SUPPORTED_BY' | 'OWNS' | 'AFFECTS' | 'PROPOSED' | 'ALIGNED_WITH' | string;
  color: string;
  dashed?: boolean;
  highlighted?: boolean;
  dimmed?: boolean;
}

export interface TimelineItem {
  id: string;
  title: string;
  type: 'rfc' | 'superseded' | 'active';
  timestamp: string;
  author?: string;
  system: string;
  summary: string;
  status?: string;
  evidence_id?: string;
}
