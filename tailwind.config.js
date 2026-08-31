/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./templates/**/*.html", "./static/js/**/*.js"],
  theme: {
    extend: {
      colors: {
        cream: "#f4ede0",
        "bottle-green": "#20392a",
        brass: "#a3763a",
        burgundy: "#6b2632",
        charcoal: "#1a1512"
      },
      fontFamily: {
        display: ["Fraunces", "Georgia", "serif"],
        sans: ["Inter", "Arial", "sans-serif"]
      },
      boxShadow: {
        frame: "0 16px 40px rgba(26, 21, 18, 0.14)"
      },
      letterSpacing: {
        editorial: "0.16em"
      }
    }
  },
  plugins: []
};
