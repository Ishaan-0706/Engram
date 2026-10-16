import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Company Brain | Executive Dashboard',
  description: 'Enterprise Knowledge Graph, deterministic grounded evidence synthesis, and 2PC proposal state machine.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark bg-slate-950">
      <body className="bg-slate-950 text-slate-100 min-h-screen antialiased selection:bg-indigo-500/30 selection:text-indigo-200">
        {children}
      </body>
    </html>
  );
}
