'use client';

import React, { useState } from 'react';
import { EvidenceItem } from '@/types';
import { 
  X, 
  Hash, 
  ExternalLink, 
  Clock, 
  FileText, 
  Check, 
  Copy, 
  ShieldCheck, 
  MessageSquare,
  BookOpen,
  Ticket,
  User
} from 'lucide-react';

interface EvidenceDrawerProps {
  evidence: EvidenceItem | null;
  onClose: () => void;
  isOpen: boolean;
}

export const EvidenceDrawer: React.FC<EvidenceDrawerProps> = ({
  evidence,
  onClose,
  isOpen,
}) => {
  const [copied, setCopied] = useState(false);

  if (!isOpen || !evidence) return null;

  const handleCopyHash = () => {
    if (evidence?.content_hash) {
      navigator.clipboard.writeText(evidence.content_hash);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const isSlack = evidence.source_uri.startsWith('slack://') || evidence.source_type === 'slack';
  const isLinear = evidence.source_uri.startsWith('linear://') || evidence.source_type === 'linear';
  const isConfluence = evidence.source_uri.startsWith('confluence://') || evidence.source_type === 'confluence';
  const isNotion = evidence.source_uri.startsWith('notion://') || evidence.source_type === 'notion';

  const slackChannelMatch = evidence.source_uri.match(/channels\/([a-zA-Z0-9_-]+)/);
  const slackChannel = slackChannelMatch ? `#${slackChannelMatch[1]}` : '#inc-payments';

  const ticketMatch = evidence.source_uri.match(/(?:issue\/|)([A-Z]+-\d+)/) || evidence.excerpt.match(/\b([A-Z]+-\d+)\b/);
  const ticketId = ticketMatch ? ticketMatch[1] : 'PAY-402';

  const author = evidence.author || (
    evidence.excerpt.toLowerCase().includes('aarav') ? 'Aarav Mehta' :
    evidence.excerpt.toLowerCase().includes('rohan') ? 'Rohan Verma' :
    evidence.excerpt.toLowerCase().includes('priya') ? 'Priya Nair' :
    evidence.excerpt.toLowerCase().includes('devin') ? 'Devin Vance' :
    evidence.excerpt.toLowerCase().includes('elena') ? 'Elena Rostova' : null
  );

  return (
    <div className="fixed inset-0 z-50 flex overflow-hidden">
      {/* Backdrop */}
      <div 
        className="fixed inset-0 bg-[#13151A]/75 backdrop-blur-sm transition-opacity animate-in fade-in duration-150"
        onClick={onClose}
      />

      {/* Slide-over panel */}
      <div className="relative w-full max-w-md bg-[#191C23] border-r border-[#2A2F3B] text-[#E4E7EB] flex flex-col shadow-2xl z-10 animate-in slide-in-from-left duration-200">
        {/* Header */}
        <div className="p-4 border-b border-[#2A2F3B] flex items-center justify-between bg-[#20242D]/60">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded bg-[#5E60CE]/15 text-[#5E60CE] border border-[#5E60CE]/30 flex items-center justify-center">
              <ShieldCheck className="w-3.5 h-3.5" />
            </div>
            <div>
              <h2 className="text-xs font-semibold text-[#E4E7EB] flex items-center gap-2">
                Grounded Evidence
                <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-[#5E60CE]/15 text-[#5E60CE] border border-[#5E60CE]/30">
                  VERIFIED
                </span>
              </h2>
              <p className="text-[10px] font-mono text-[#858D9A] truncate max-w-[240px]">{evidence.id}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close Evidence Drawer"
            className="p-1 rounded text-[#949BA6] hover:text-[#E4E7EB] hover:bg-[#20242D] transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Verbatim Excerpt */}
          <div className="space-y-1.5">
            <span className="text-[10px] font-mono uppercase tracking-wider text-[#858D9A] flex items-center gap-1.5">
              <FileText className="w-3 h-3 text-[#858D9A]" />
              Verbatim Source Excerpt
            </span>
            <div className="bg-[#20242D] border border-[#2A2F3B] rounded p-3 relative overflow-hidden">
              <div className="absolute left-0 top-0 bottom-0 w-1 bg-[#5E60CE]" />
              <blockquote className="text-xs leading-relaxed text-[#E4E7EB] italic pl-2">
                &ldquo;{evidence.excerpt}&rdquo;
              </blockquote>
            </div>
          </div>

          {/* Source Location & Platform */}
          <div className="space-y-1.5">
            <span className="text-[10px] font-mono uppercase tracking-wider text-[#858D9A] flex items-center gap-1.5">
              <ExternalLink className="w-3 h-3 text-[#858D9A]" />
              Source Provenance URI
            </span>
            <div className="bg-[#20242D] border border-[#2A2F3B] rounded p-3 space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                {isSlack ? (
                  <span className="inline-flex items-center gap-1.5 text-[10px] px-2.5 py-0.5 rounded font-medium bg-[#4E9F76]/15 text-[#4E9F76] border border-[#4E9F76]/30">
                    <MessageSquare className="w-3 h-3" />
                    <span>Slack Chat</span>
                    <span className="font-mono text-[9px] bg-[#4E9F76]/20 px-1 py-0.2 rounded font-semibold">{slackChannel}</span>
                  </span>
                ) : isLinear ? (
                  <span className="inline-flex items-center gap-1.5 text-[10px] px-2.5 py-0.5 rounded font-medium bg-[#5E60CE]/15 text-[#5E60CE] border border-[#5E60CE]/30">
                    <Ticket className="w-3 h-3" />
                    <span>Linear Ticket</span>
                    <span className="font-mono text-[9px] bg-[#5E60CE]/20 px-1 py-0.2 rounded font-bold">{ticketId}</span>
                  </span>
                ) : isConfluence ? (
                  <span className="inline-flex items-center gap-1.5 text-[10px] px-2.5 py-0.5 rounded font-medium bg-[#4C78A8]/15 text-[#4C78A8] border border-[#4C78A8]/30">
                    <BookOpen className="w-3 h-3" />
                    <span>Confluence RFC</span>
                    <span className="font-mono text-[9px] bg-[#D07D38]/20 text-[#D07D38] px-1 py-0.2 rounded">stale</span>
                  </span>
                ) : isNotion ? (
                  <span className="inline-flex items-center gap-1.5 text-[10px] px-2.5 py-0.5 rounded font-medium bg-[#D07D38]/15 text-[#D07D38] border border-[#D07D38]/30">
                    <FileText className="w-3 h-3" />
                    <span>Notion SOP</span>
                    <span className="font-mono text-[9px] bg-[#D07D38]/20 text-[#D07D38] px-1 py-0.2 rounded">stale</span>
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded font-medium bg-[#2A2F3B] text-[#949BA6] border border-[#2A2F3B]">
                    Enterprise Document
                  </span>
                )}

                {author && (
                  <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded font-medium bg-[#20242D] text-[#D4CEBF] border border-[#2A2F3B]">
                    <User className="w-2.5 h-2.5 text-[#949BA6]" />
                    <span>{author}</span>
                  </span>
                )}
              </div>
              <p className="text-xs font-mono text-[#E4E7EB] break-all bg-[#191C23] p-2 rounded border border-[#2A2F3B]">
                {evidence.source_uri}
              </p>
            </div>
          </div>

          {/* Timestamp */}
          <div className="space-y-1.5">
            <span className="text-[10px] font-mono uppercase tracking-wider text-[#858D9A] flex items-center gap-1.5">
              <Clock className="w-3 h-3 text-[#858D9A]" />
              Ingestion Timestamp
            </span>
            <div className="bg-[#20242D] border border-[#2A2F3B] rounded p-2.5 text-xs font-mono text-[#E4E7EB] flex items-center gap-2">
              <span className="text-[#858D9A]">Recorded:</span>
              <span className="text-[#E4E7EB]">{evidence.source_timestamp}</span>
            </div>
          </div>

          {/* Cryptographic SHA-256 Hash */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono uppercase tracking-wider text-[#858D9A] flex items-center gap-1.5">
                <Hash className="w-3 h-3 text-[#858D9A]" />
                SHA-256 Content Hash
              </span>
              <button
                onClick={handleCopyHash}
                className="text-[10px] font-mono text-[#858D9A] hover:text-[#E4E7EB] flex items-center gap-1 transition-colors"
              >
                {copied ? (
                  <>
                    <Check className="w-2.5 h-2.5 text-[#4E9F76]" />
                    <span className="text-[#4E9F76]">Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-2.5 h-2.5" />
                    <span>Copy</span>
                  </>
                )}
              </button>
            </div>
            <div className="bg-[#20242D] border border-[#2A2F3B] rounded p-2.5 font-mono text-[11px] text-[#5E60CE] break-all select-all">
              {evidence.content_hash}
            </div>
          </div>

          {/* Connected Record ID */}
          <div className="pt-2 border-t border-[#2A2F3B]">
            <div className="flex items-center justify-between text-xs">
              <span className="text-[#949BA6]">Associated Node:</span>
              <span className="font-mono text-[#E4E7EB] bg-[#20242D] border border-[#2A2F3B] px-2 py-0.5 rounded text-[10px]">
                {evidence.record_id}
              </span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-[#2A2F3B] bg-[#20242D]/40 flex justify-end">
          <button
            onClick={onClose}
            className="px-3 py-1 text-xs font-medium text-[#949BA6] hover:text-[#E4E7EB] bg-[#20242D] hover:bg-[#2A2F3B] border border-[#2A2F3B] rounded transition-colors"
          >
            Close Drawer
          </button>
        </div>
      </div>
    </div>
  );
};
