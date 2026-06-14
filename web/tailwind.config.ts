import type { Config } from "tailwindcss";

// MIDAS theme tokens. Mirrors the palette in the legacy CSS — restrained, data-first,
// the only accent is Proof-First green. Light + dark via prefers-color-scheme (the
// .dark class is also honored so we can flip explicitly in Settings later).
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["media", "class"],
  theme: {
    container: { center: true, padding: "1.5rem", screens: { "2xl": "1280px" } },
    extend: {
      colors: {
        ink: "hsl(var(--ink))",
        paper: "hsl(var(--paper))",
        rule: "hsl(var(--rule))",
        "rule-soft": "hsl(var(--rule-soft))",
        mute: "hsl(var(--mute))",
        accent: { DEFAULT: "hsl(var(--accent))", hi: "hsl(var(--accent-hi))" },
        warn: { DEFAULT: "hsl(var(--warn))", hi: "hsl(var(--warn-hi))" },
        "ok-bg": "hsl(var(--ok-bg))",
        "warn-bg": "hsl(var(--warn-bg))",
      },
      fontFamily: {
        ui: ["Geist", "ui-sans-serif", "-apple-system", "Segoe UI", "Inter", "Roboto", "sans-serif"],
        mono: [
          "Geist Mono",
          "ui-monospace",
          "JetBrains Mono",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
        display: ["EB Garamond", "Iowan Old Style", "Georgia", "serif"],
      },
      borderRadius: { sm: "0", md: "0", lg: "0" }, // sharp by intention
      fontVariantNumeric: { tabular: "tabular-nums" },
    },
  },
  plugins: [],
} satisfies Config;
