'use client';

import React from 'react';
import { Tenant } from '@/types';
import { 
  Database, 
  ChevronDown,
  Terminal
} from 'lucide-react';

interface TopBarProps {
  currentTenant: Tenant;
  onTenantChange: (tenant: Tenant) => void;
  epoch: number;
  isConnected: boolean;
  status: string;
}

export const TopBar: React.FC<TopBarProps> = ({
  currentTenant,
  onTenantChange,
  epoch,
  isConnected,
}) => {
  const primarySystem = currentTenant === 'Nexus Infra' ? 'event-stream-cluster' : 'payment-gateway';

  return (
    <header className="h-12 border-b border-[#2A2F3B] bg-[#191C23] px-4 flex items-center justify-between select-none z-30 sticky top-0">
      {/* Left: Minimalist logomark + crisp title + subtle breadcrumb */}
      <div className="flex items-center gap-3">
        <div className="w-6 h-6 rounded bg-[#20242D] border border-[#2A2F3B] flex items-center justify-center">
          <Terminal className="w-3.5 h-3.5 text-[#4C78A8]" />
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="font-semibold text-[#E4E7EB] tracking-tight">Engram</span>
          <span className="text-[#858D9A]">/</span>
          <span className="text-[#949BA6] font-mono text-[11px]">
            {currentTenant} <span className="text-[#858D9A]">/</span> {primarySystem}
          </span>
        </div>
      </div>

      {/* Center: Tenant Switcher dropdown */}
      <div className="flex items-center gap-1.5 bg-[#20242D] border border-[#2A2F3B] rounded px-2.5 py-1 text-xs text-[#E4E7EB]">
        <Database className="w-3.5 h-3.5 text-[#858D9A]" />
        <div className="relative flex items-center">
          <select
            value={currentTenant}
            onChange={(e) => onTenantChange(e.target.value as Tenant)}
            aria-label="Select Tenant Scope"
            className="bg-transparent text-xs font-medium cursor-pointer focus:outline-none appearance-none pr-4 text-[#E4E7EB]"
          >
            <option value="Acme Payments" className="bg-[#20242D] text-[#E4E7EB]">Acme Payments</option>
            <option value="Nexus Infra" className="bg-[#20242D] text-[#E4E7EB]">Nexus Infra</option>
          </select>
          <ChevronDown className="w-3 h-3 text-[#858D9A] pointer-events-none -ml-3" />
        </div>
      </div>

      {/* Right: Connection Indicator & Epoch Counter */}
      <div className="flex items-center gap-3">
        {/* Minimal connection indicator */}
        <div className="flex items-center gap-1.5 text-[11px] font-mono text-[#949BA6]">
          <span
            className={`w-2 h-2 rounded-full ${
              isConnected ? 'bg-[#4E9F76] shadow-[0_0_8px_rgba(78,159,118,0.4)]' : 'bg-[#68707E]'
            }`}
          />
          <span className={isConnected ? 'text-[#E4E7EB]' : 'text-[#858D9A]'}>
            {isConnected ? 'FalkorDB Live • 6379' : 'FalkorDB Offline • 6379'}
          </span>
        </div>

        <div className="h-3 w-px bg-[#2A2F3B]" />

        {/* Current turn counter tag */}
        <div className="px-2 py-0.5 rounded bg-[#20242D] border border-[#2A2F3B] text-[11px] font-mono text-[#858D9A]">
          epoch: <span className="text-[#E4E7EB]">{epoch}</span>
        </div>
      </div>
    </header>
  );
};
