import React, { createContext, useContext, useState, ReactNode } from "react";

export interface TenantContextType {
  activeTenant: string;
  setActiveTenant: (tenant: string) => void;
  availableTenants: { id: string; name: string }[];
}

const DEFAULT_TENANTS = [
  { id: "acme_payments", name: "Acme Payments (Financial)" },
  { id: "nexus_infra", name: "Nexus Infra (Platform Engineering)" },
];

const TenantContext = createContext<TenantContextType | undefined>(undefined);

export function TenantProvider({ children }: { children: ReactNode }) {
  const [activeTenant, setActiveTenant] = useState<string>("acme_payments");

  return (
    <TenantContext.Provider
      value={{
        activeTenant,
        setActiveTenant,
        availableTenants: DEFAULT_TENANTS,
      }}
    >
      {children}
    </TenantContext.Provider>
  );
}

export function useTenant(): TenantContextType {
  const context = useContext(TenantContext);
  if (!context) {
    throw new Error("useTenant must be used within a TenantProvider");
  }
  return context;
}
