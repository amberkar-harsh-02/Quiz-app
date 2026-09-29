/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: '#172033',      // body text; also the host stage in a lighter room
        stage: '#0F1B2D',    // projector background for the live game
        paper: '#F3F5F8',    // page background
        line: '#D5DCE5',     // borders and dividers
        muted: '#5A6779',    // secondary text
        brand: {
          DEFAULT: '#1F4F8F',
          dark: '#173D70',
          soft: '#E4ECF6',
        },
        ok: { DEFAULT: '#1E7A3E', soft: '#E3F2E8' },
        bad: { DEFAULT: '#B42318', soft: '#FBE9E7' },
        warn: { DEFAULT: '#9A6700', soft: '#FCF3DC' },
      },
      fontFamily: {
        sans: ['"Atkinson Hyperlegible Next Variable"', 'system-ui', 'sans-serif'],
        mono: ['"Atkinson Hyperlegible Mono"', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        chip: '8px',
        control: '12px',
        panel: '16px',
      },
      keyframes: {
        pop: {
          '0%': { opacity: '0', transform: 'scale(0.9)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        bump: {
          '0%, 100%': { transform: 'scale(1)' },
          '50%': { transform: 'scale(1.08)' },
        },
        rise: {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'grow-x': {
          '0%': { transform: 'scaleX(0)' },
          '100%': { transform: 'scaleX(1)' },
        },
        'slide-down': {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(0)' },
        },
        dim: {
          '0%': { opacity: '1' },
          '100%': { opacity: '0.5' },
        },
        settle: {
          '0%': { opacity: '0', transform: 'scale(0.96)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
      },
      animation: {
        pop: 'pop 180ms ease-out both',
        bump: 'bump 150ms ease-out',
        rise: 'rise 220ms ease-out both',
        'grow-x': 'grow-x 500ms cubic-bezier(0.2, 0.7, 0.2, 1) both',
        'slide-down': 'slide-down 180ms ease-out both',
        settle: 'settle 200ms ease-out both',
        dim: 'dim 300ms ease-out 300ms both',
      },
    },
  },
  plugins: [],
}
