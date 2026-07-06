import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["Inter", "Segoe UI", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Cascadia Code", "Consolas", "monospace"],
      },
      colors: {
        hull: "#050706",
        glass: "rgba(9, 18, 19, 0.72)",
        cyanline: "#3ee7f0",
        reactor: "#ffce5c",
        alert: "#ff5d5d",
        matrix: "#6dffb8",
      },
    },
  },
  plugins: [],
} satisfies Config;
