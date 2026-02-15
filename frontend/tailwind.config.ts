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
        asahi: {
          orange: "#FF6B35",
          "orange-light": "#FFB84D",
          "orange-very-light": "#FFF3E0",
        },
        neutral: {
          dark: "#1A1A1A",
          "dark-gray": "#4A4A4A",
          "light-gray": "#F5F5F5",
          border: "#E0E0E0",
          white: "#FFFFFF",
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
