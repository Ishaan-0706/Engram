from __future__ import annotations

from app.contracts import validate


class TenantAuthError(Exception):
    pass


def graph_key_from_claims(claims: dict) -> str:
    validate("jwt-tenant-claims", claims)
    tid = claims["tid"]
    if not tid:
        raise TenantAuthError("missing tid")
    return f"tenant:{tid}"
