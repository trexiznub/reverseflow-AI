import type { Config } from "tailwindcss";

// Monochrome, high-contrast dark theme. Token names are kept from the first
// design so components did not need renaming:
//   white   -> panel surface        canvas -> subtle fill / hover
//   ink-*   -> text, light to dim    line   -> hairlines
//   navy-*  -> "inverted" strong elements (light on dark)
//   blue-*  -> primary actions, also monochrome (white buttons, dark text)
// Status colours are the only hues, and are used only to mean something.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        white: "#0B0B0B",
        black: "#000000",
        paper: "#FFFFFF",
        navy: { 950: "#000000", 900: "#F2F2F2", 800: "#D4D4D4", 700: "#B5B5B5", 600: "#9A9A9A" },
        blue: { 50: "#181818", 100: "#262626", 200: "#3A3A3A", 400: "#BDBDBD", 500: "#F2F2F2", 600: "#FFFFFF", 700: "#E8E8E8" },
        ink: { 900: "#F4F4F4", 700: "#CCCCCC", 500: "#9A9A9A", 400: "#777777", 300: "#4D4D4D" },
        line: { DEFAULT: "#232323", strong: "#363636" },
        canvas: "#151515",
        ok: { 50: "#0F1F17", 600: "#3FBF7F", 700: "#74D9A5" },
        warn: { 50: "#231B0B", 500: "#E3A33B", 700: "#F2C26E" },
        bad: { 50: "#26120F", 600: "#F0583E", 700: "#FF8F7A" },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
        display: ["var(--font-display)", "var(--font-sans)", "sans-serif"],
      },
      fontSize: { "2xs": ["10.5px", "14px"] },
      borderRadius: { DEFAULT: "5px", md: "7px", lg: "10px", xl: "14px" },
      boxShadow: { pop: "0 18px 50px -12px rgba(0,0,0,.8), 0 0 0 1px #2A2A2A" },
      keyframes: {
        dash: { to: { strokeDashoffset: "-24" } },
        pulseRing: { "0%": { transform: "scale(.6)", opacity: ".7" }, "100%": { transform: "scale(1.9)", opacity: "0" } },
        blink: { "0%,100%": { opacity: "1" }, "50%": { opacity: ".25" } },
      },
      animation: { dash: "dash 1.2s linear infinite", ring: "pulseRing 2.2s ease-out infinite", blink: "blink 1.6s ease-in-out infinite" },
    },
  },
  plugins: [],
};
export default config;
