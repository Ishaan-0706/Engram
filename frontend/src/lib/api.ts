import { TurnState } from '@/types';
import { generateUUIDv7 } from './uuid';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface TurnResponsePayload {
  turn: TurnState;
  epoch: number;
}

export interface ConfirmResponsePayload {
  status: string;
  idempotency_key: string;
  executed: boolean;
  result: Record<string, any>;
  epoch?: number;
}

export interface ErrorConflictPayload {
  error: string;
  current_snapshot_hash: string;
  epoch: number;
}

export async function executeTurn(
  tenantId: string,
  sessionId: string,
  userQuery: string,
  epoch: number
): Promise<TurnResponsePayload> {
  const res = await fetch(`${API_BASE}/api/turn`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tenant_id: tenantId,
      session_id: sessionId,
      user_query: userQuery,
      epoch: epoch,
    }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const err = new Error(errorData.detail?.error || errorData.detail || `Turn failed (${res.status})`);
    (err as any).status = res.status;
    (err as any).data = errorData;
    throw err;
  }

  return res.json();
}

export async function resumeTurn(
  tenantId: string,
  sessionId: string,
  lastKnownEpoch: number
): Promise<TurnState> {
  const res = await fetch(`${API_BASE}/api/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tenant_id: tenantId,
      session_id: sessionId,
      last_known_epoch: lastKnownEpoch,
    }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const err = new Error(errorData.detail?.error || 'Resume failed');
    (err as any).status = res.status;
    (err as any).data = errorData;
    throw err;
  }

  return res.json();
}

export async function confirmProposal(
  tenantId: string,
  sessionId: string,
  proposalId: string,
  snapshotHash: string,
  idempotencyKey?: string
): Promise<ConfirmResponsePayload> {
  const key = idempotencyKey || generateUUIDv7();
  const res = await fetch(`${API_BASE}/api/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tenant_id: tenantId,
      session_id: sessionId,
      proposal_id: proposalId,
      snapshot_hash: snapshotHash,
      idempotency_key: key,
    }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const err = new Error(errorData.detail?.error || errorData.error || `Confirm failed (${res.status})`);
    (err as any).status = res.status;
    (err as any).data = errorData.detail || errorData;
    throw err;
  }

  return res.json();
}

export async function checkConnection(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tenant_id: 'health_check',
        session_id: 'ping',
        last_known_epoch: 0,
      }),
    });
    // Even a 410 or 404 response means the server is reachable and active!
    return res.status === 410 || res.status === 200 || res.status === 404;
  } catch {
    return false;
  }
}
