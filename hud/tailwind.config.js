/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      keyframes: {
        spotlight: {
          '0%': {
            opacity: '0',
            transform: 'translate3d(-72px, -28px, 0) scale(0.92)',
          },
          '25%': {
            opacity: '0.22',
          },
          '55%': {
            opacity: '0.38',
            transform: 'translate3d(0, 0, 0) scale(1)',
          },
          '100%': {
            opacity: '0.2',
            transform: 'translate3d(44px, 18px, 0) scale(1.04)',
          },
        },
        moveHorizontal: {
          '0%': {
            transform: 'translateX(-50%) translateY(-10%)',
          },
          '50%': {
            transform: 'translateX(50%) translateY(10%)',
          },
          '100%': {
            transform: 'translateX(-50%) translateY(-10%)',
          },
        },
        moveInCircle: {
          '0%': {
            transform: 'rotate(0deg)',
          },
          '50%': {
            transform: 'rotate(180deg)',
          },
          '100%': {
            transform: 'rotate(360deg)',
          },
        },
        moveVertical: {
          '0%': {
            transform: 'translateY(-50%)',
          },
          '50%': {
            transform: 'translateY(50%)',
          },
          '100%': {
            transform: 'translateY(-50%)',
          },
        },
      },
      animation: {
        spotlight: 'spotlight 7.4s cubic-bezier(0.22, 1, 0.36, 1) infinite alternate',
        first: 'moveVertical 30s ease infinite',
        second: 'moveInCircle 20s reverse infinite',
        third: 'moveInCircle 40s linear infinite',
        fourth: 'moveHorizontal 40s ease infinite',
        fifth: 'moveInCircle 20s ease infinite',
      },
    },
  },
  plugins: [],
}
