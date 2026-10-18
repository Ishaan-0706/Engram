import { API_BASE_URL } from "./config";

export interface TurnRequest {
  tenant_id: string;
  session_id: string;
  user_query: string;
  epoch: number;
}

export interface TurnResponse {
  turn: Record<string, unknown>;
  epoch: number;
}

export interface ConfirmRequest {
  tenant_id: string;
  session_id: string;
  proposal_id: string;
  snapshot_hash: string;
  idempotency_key: string;
}

export interface ResumeRequest {
  tenant_id: string;
  session_id: string;
  last_known_epoch: number;
}

/**
 * Run one agent turn for the given dynamic tenant.
 */
export async function postTurn(request: TurnRequest): Promise<TurnResponse> {
  const resp = await fetch(`${API_BASE_URL}/api/turn`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const errorBody = await resp.json().catch(() => ({}));
    throw new Error(`Turn failed (${resp.status}): ${JSON.stringify(errorBody)}`);
  }
  return resp.json();
}

/**
 * Confirm a pending proposal for the given dynamic tenant.
 */
export async function confirmProposal(
  request: ConfirmRequest
): Promise<Record<string, unknown>> {
  const resp = await fetch(`${API_BASE_URL}/api/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const errorBody = await resp.json().catch(() => ({}));
    throw new Error(`Confirm failed (${resp.status}): ${JSON.stringify(errorBody)}`);
  }
  return resp.json();
}

/**
 * Fetch live graph topology (nodes, links, timeline) for tenant from FalkorDB.
 */
export async function fetchGraphTopology(
  tenantId: string
): Promise<{ tenant_id: string; nodes: any[]; links: any[]; timeline: any[] }> {
  const normalized = tenantId.toLowerCase().replace(/\s+/g, "_");
  const resp = await fetch(`${API_BASE_URL}/api/graph/${normalized}`);
  if (!resp.ok) {
    const errorBody = await resp.json().catch(() => ({}));
    throw new Error(`Graph fetch failed (${resp.status}): ${JSON.stringify(errorBody)}`);
  }
  return resp.json();
}

