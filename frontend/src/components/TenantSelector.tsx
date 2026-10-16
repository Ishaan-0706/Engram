import React from "react";
import { useTenant } from "../context/TenantContext";

export function TenantSelector() {
  const { activeTenant, setActiveTenant, availableTenants } = useTenant();

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
      <label htmlFor="tenant-select" style={{ fontWeight: 600, fontSize: "14px" }}>
        Active Tenant:
      </label>
      <select
        id="tenant-select"
        value={activeTenant}
        onChange={(e) => setActiveTenant(e.target.value)}
        style={{
          padding: "6px 12px",
          borderRadius: "6px",
          border: "1px solid #ccc",
          backgroundColor: "#fff",
          fontSize: "14px",
          cursor: "pointer",
        }}
      >
        {availableTenants.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
          </option>
        ))}
      </select>
    </div>
  );
}
