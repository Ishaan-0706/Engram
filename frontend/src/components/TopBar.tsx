'use client';

import React from 'react';
import { Tenant } from '@/types';
import { 
  Building2, 
  ShieldCheck, 
  Layers, 
  Activity, 
  Cpu,
  ChevronDown
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
  status,
}) => {
  return (
    <header className="h-14 border-b border-slate-800 bg-slate-950/90 backdrop-blur-md px-4 flex items-center justify-between select-none z-30 sticky top-0">
      {/* Brand & Workspace Title */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <Cpu className="w-4 h-4 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-semibold tracking-tight text-white flex items-center gap-1.5">
              Company Brain
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                v1.0-EXEC
              </span>
            </h1>
            <p className="text-[11px] text-slate-400 font-medium">Enterprise Knowledge Graph & Grounded Agent</p>
          </div>
        </div>

        <div className="h-4 w-px bg-slate-800 mx-1" />

        {/* Tenant Switcher */}
        <div className="relative group">
          <label className="text-[10px] uppercase font-mono tracking-wider text-slate-400 block -mb-0.5">
            Tenant Scope
          </label>
          <div className="flex items-center gap-1.5 bg-slate-900 hover:bg-slate-850 border border-slate-700/80 rounded-md px-2.5 py-1 text-xs text-slate-200 transition-colors shadow-sm">
            <Building2 className="w-3.5 h-3.5 text-indigo-400" />
            <select
              value={currentTenant}
              onChange={(e) => onTenantChange(e.target.value as Tenant)}
              aria-label="Select Tenant Scope"
              className="bg-transparent font-medium cursor-pointer focus:outline-none appearance-none pr-5 text-slate-100"
            >
              <option value="Acme Payments" className="bg-slate-900 text-slate-100">Acme Payments</option>
              <option value="Nexus Infra" className="bg-slate-900 text-slate-100">Nexus Infra</option>
            </select>
            <ChevronDown className="w-3 h-3 text-slate-400 pointer-events-none -ml-4" />
          </div>
        </div>
      </div>

      {/* Badges & Status Controls */}
      <div className="flex items-center gap-3">
        {/* Persona Badge */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-900 border border-slate-800 text-xs text-slate-300 shadow-sm">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
          <span className="text-slate-400 font-mono text-[11px]">Viewing as:</span>
          <span className="font-semibold text-slate-200">Staff Engineer</span>
        </div>

        {/* Status Tag */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-900 border border-slate-800 text-xs text-slate-300 shadow-sm">
          <span className="text-slate-400 font-mono text-[11px]">Turn Status:</span>
          <span
            className={`font-mono font-semibold uppercase text-[11px] px-1.5 py-0.5 rounded ${
              status === 'COMPLETED'
                ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                : status === 'AWAITING_CONFIRMATION'
                ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30 animate-pulse'
                : status === 'FAILED'
                ? 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
                : status === 'EXECUTING_TOOLS'
                ? 'bg-indigo-500/15 text-indigo-400 border border-indigo-500/30 animate-pulse'
                : 'bg-slate-800 text-slate-300'
            }`}
          >
            {status}
          </span>
        </div>

        {/* Epoch Counter Badge */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-900 border border-slate-800 text-xs shadow-sm">
          <Layers className="w-3.5 h-3.5 text-violet-400" />
          <span className="text-slate-400 font-mono text-[11px]">Epoch:</span>
          <span className="font-mono font-bold text-violet-300 bg-violet-950/60 px-1.5 py-0.2 rounded border border-violet-800/40">
            #{epoch}
          </span>
        </div>

        {/* Connection Status Indicator */}
        <div className="flex items-center gap-2 pl-2 border-l border-slate-800">
          <div className="relative flex items-center justify-center">
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                isConnected ? 'bg-emerald-500' : 'bg-rose-500'
              }`}
            />
            {isConnected && (
              <span className="absolute w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping opacity-75" />
            )}
          </div>
          <span className="text-[11px] font-mono text-slate-300">
            {isConnected ? 'FastAPI Connected' : 'Offline / Mock Demo'}
          </span>
        </div>
      </div>
    </header>
  );
};
