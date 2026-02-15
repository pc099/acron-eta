import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        acron: {
          primary: "#FFFFFF",
          black: "#0f0f0f",
          dark: "#141414",
          light: "#FFFFFF",
          gray: "#2a2a2a",
          primary_accent: "#D97B4A", // Soothing orange, not too bright
        },
        "asahi-orange": "#D97B4A",
        "asahi-orange-very-light": "rgba(217,123,74,0.15)",
        neutral: {
          dark: "#141414",
          "dark-gray": "#9CA3AF",
          "light-gray": "#1e1e1e",
          border: "#2d2d2d",
          white: "#141414",
        },
        semantic: {
          success: "#4CAF50",
          error: "#F44336",
          warning: "#FF9800",
          info: "#2196F3",
        },
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "sans-serif"],
      },
      fontSize: {
        h1: ["48px", { lineHeight: "1.2", fontWeight: "700" }],
        h2: ["36px", { lineHeight: "1.3", fontWeight: "700" }],
        h3: ["28px", { lineHeight: "1.4", fontWeight: "700" }],
        h4: ["24px", { lineHeight: "1.4", fontWeight: "600" }],
      },
      spacing: {
        sidebar: "256px",
      },
      borderRadius: {
        card: "8px",
        button: "8px",
      },
    },
  },
  plugins: [],
};

export default config;
