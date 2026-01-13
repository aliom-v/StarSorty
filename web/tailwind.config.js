/** @type {import("tailwindcss").Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        display: ["Space Grotesk", "system-ui", "sans-serif"],
        body: ["IBM Plex Sans", "system-ui", "sans-serif"]
      },
      colors: {
        ink: "rgb(var(--ink) / <alpha-value>)",
        sand: "rgb(var(--sand) / <alpha-value>)",
        clay: "rgb(var(--clay) / <alpha-value>)",
        moss: "rgb(var(--moss) / <alpha-value>)",
        copper: "rgb(var(--copper) / <alpha-value>)",
        sky: "rgb(var(--sky) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        "surface-muted": "rgb(var(--surface-muted) / <alpha-value>)"
      },
      boxShadow: {
        soft: "0 20px 60px -30px rgba(12, 10, 9, 0.35)"
      }
    }
  },
  plugins: []
};
