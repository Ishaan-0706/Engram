import type { Metadata } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import './globals.css';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-sans',
  display: 'swap',
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-mono',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'Engram | Enterprise Knowledge Architecture (FalkorDB)',
  description: 'Enterprise Knowledge Graph, deterministic grounded evidence synthesis, and 2PC proposal state machine.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`dark ${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="bg-[#13151A] text-[#E4E7EB] min-h-screen antialiased font-sans selection:bg-[#4C78A8]/25 selection:text-[#E4E7EB]">
        {children}
      </body>
    </html>
  );
}
