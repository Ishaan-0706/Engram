import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: "#13151A",       // Deep Graphite
        panel: "#191C23",        // Machined Charcoal
        elevated: "#20242D",     // Elevated Slate
        borderIron: "#2A2F3B",   // Hairline Iron
        borderHover: "#3E4554",
        textPrimary: "#E4E7EB",  // Warm Off-White
        textSecondary: "#949BA6",// Muted Stone
        textMono: "#858D9A",     // Monospace Metadata
        entity: {
          system: "#4C78A8",         // Deep Steel Blue
          activeDecision: "#4E9F76", // Muted Forest / Sage Green
          superseded: "#68707E",     // Ash Gray
          staleDoc: "#D07D38",       // Warm Clay / Ochre
          evidence: "#5E60CE",       // Deep Periwinkle / Slate Indigo
          person: "#D4CEBF",         // Warm Sandstone
        },
        relation: {
          supersedes: "#B84A39",     // Muted Brick Red
          supported: "#5E60CE",      // Solid Indigo Slate
          standard: "#323744",       // Subdued Iron Gray
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "SFMono-Regular", "Menlo", "Monaco", "Consolas", "monospace"],
      },
      borderColor: {
        subtle: "#2A2F3B",
      },
    },
  },
  plugins: [],
};
export default config;
