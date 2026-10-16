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
        entity: {
          person: "#3b82f6",     // blue
          system: "#10b981",     // emerald
          decision: "#8b5cf6",   // violet
          document: "#f59e0b",   // amber
          evidence: "#eab308",   // yellow
        },
        relation: {
          supersedes: "#ef4444", // dashed red
          supported: "#eab308",  // solid gold
        },
      },
    },
  },
  plugins: [],
};
export default config;
