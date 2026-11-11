import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      colors: {
        brand: {
          400: "#39d987",
          500: "#06c96c",
          600: "#059c5a",
          700: "#048a52",
        },
        cyber: {
          green: "#06c96c",
          dark: "#059c5a",
          bg: "#0f1419",
        },
      },
      maxWidth: {
        cyber: "1200px",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        float: "float-y 6s ease-in-out infinite",
      },
      keyframes: {
        "float-y": {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-8px)" },
        },
      },
    },
  },
  plugins: [],
};
export default config;
