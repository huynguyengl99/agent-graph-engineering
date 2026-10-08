/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
    // Streamdown styles what it renders with Tailwind classes of its own.
    "./node_modules/streamdown/dist/*.js",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
