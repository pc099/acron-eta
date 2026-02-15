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
          primary: "#FFFFFF", // White for primary accents in a black theme? or maybe a specific brand color. Let's stick to standard dark mode patterns.
          // User asked for "black as background".
          // Let's define a 'black' palette or just use neutral.
          // But replacing 'asahi' structure:
          black: "#000000",
          dark: "#0A0A0A",
          light: "#FFFFFF",
          gray: "#333333",
          primary_accent: "#FF6B35", // Keeping the orange as an accent for now unless specified otherwise, or maybe the user wants purely black/white.
          // "check the above image for sing in i need the singn in and sign up pages to be in the same way"
          // The image usually implies a clean dark mode.
        },
        neutral: {
          dark: "#050505", // Deep black/gray
          "dark-gray": "#9CA3AF", // Lighter gray for text
          "light-gray": "#1F2937", // Dark gray for containers
          border: "#374151",
          white: "#000000", // Inverting for dark mode? No, better to stick to semantic names.
          // Let's redefine neutral to be dark-mode friendly defaults
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
