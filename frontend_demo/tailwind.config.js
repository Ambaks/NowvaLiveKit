/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: {
          DEFAULT: '#0A0A0B',
          secondary: '#111113',
          tertiary: '#1A1A1F',
        },
        surface: {
          DEFAULT: '#141416',
          light: '#1E1E22',
        },
        foreground: {
          DEFAULT: '#F5F5F7',
          secondary: '#8E8E93',
          tertiary: '#48484A',
        },
        accent: {
          DEFAULT: '#00E5FF',
          hover: '#00B8D4',
          light: '#67FFFF',
          dark: '#0097A7',
        },
        cta: {
          DEFAULT: '#FFB800',
          hover: '#FFA000',
          light: '#FFCA28',
          dark: '#FF8F00',
        },
        border: {
          DEFAULT: '#2A2A2E',
          light: '#3A3A3E',
        },
        success: '#10B981',
        warning: '#F59E0B',
        danger: '#EF4444',
      },
      fontFamily: {
        display: ['Syne', 'system-ui', 'sans-serif'],
        sans: ['Plus Jakarta Sans', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      fontSize: {
        'display-2xl': ['8rem', { lineHeight: '0.95', letterSpacing: '-0.04em' }],
        'display-xl': ['5.5rem', { lineHeight: '0.95', letterSpacing: '-0.03em' }],
        'display-lg': ['4rem', { lineHeight: '1.0', letterSpacing: '-0.03em' }],
        'display-md': ['3rem', { lineHeight: '1.1', letterSpacing: '-0.02em' }],
        'heading-xl': ['2.25rem', { lineHeight: '1.2', letterSpacing: '-0.01em' }],
        'heading-lg': ['1.875rem', { lineHeight: '1.3' }],
        'heading-md': ['1.5rem', { lineHeight: '1.4' }],
        'body-lg': ['1.125rem', { lineHeight: '1.7' }],
        'body-md': ['1rem', { lineHeight: '1.7' }],
        'body-sm': ['0.875rem', { lineHeight: '1.6' }],
        'caption': ['0.75rem', { lineHeight: '1.4', letterSpacing: '0.05em' }],
        'eyebrow': ['0.8125rem', { lineHeight: '1.2', letterSpacing: '0.2em' }],
      },
      spacing: {
        '18': '4.5rem',
        '88': '22rem',
        '100': '25rem',
        '128': '32rem',
      },
      maxWidth: {
        '8xl': '88rem',
        '9xl': '96rem',
      },
      borderRadius: {
        'xl': '1rem',
        '2xl': '1.5rem',
      },
      boxShadow: {
        'glow-cyan': '0 0 20px rgba(0, 229, 255, 0.2)',
        'glow-cyan-lg': '0 0 40px rgba(0, 229, 255, 0.3)',
        'glow-amber': '0 0 20px rgba(255, 184, 0, 0.25)',
        'glow-amber-lg': '0 0 40px rgba(255, 184, 0, 0.35)',
        'elevation-1': '0 1px 3px rgba(0, 0, 0, 0.5), 0 1px 2px rgba(0, 0, 0, 0.4)',
        'elevation-2': '0 4px 12px rgba(0, 0, 0, 0.5), 0 2px 4px rgba(0, 0, 0, 0.4)',
        'elevation-3': '0 12px 40px rgba(0, 0, 0, 0.6), 0 4px 12px rgba(0, 0, 0, 0.4)',
      },
      animation: {
        'fade-in': 'fadeIn 0.6s ease-out forwards',
        'slide-up': 'slideUp 0.6s ease-out forwards',
        'slide-down': 'slideDown 0.6s ease-out forwards',
        'scale-in': 'scaleIn 0.4s ease-out forwards',
        'gradient-x': 'gradientX 3s ease infinite',
        'shimmer': 'shimmer 2s linear infinite',
        'grid-pulse': 'gridPulse 4s ease-in-out infinite',
        'line-draw': 'lineDraw 1.5s ease-out forwards',
        'scan': 'scan 3s ease-in-out infinite',
        'glow-pulse': 'glowPulse 2s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        slideDown: {
          '0%': { transform: 'translateY(-20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        scaleIn: {
          '0%': { transform: 'scale(0.95)', opacity: '0' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
        gradientX: {
          '0%, 100%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' },
        },
        shimmer: {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(100%)' },
        },
        gridPulse: {
          '0%, 100%': { opacity: '0.03' },
          '50%': { opacity: '0.08' },
        },
        lineDraw: {
          '0%': { strokeDashoffset: '100%' },
          '100%': { strokeDashoffset: '0%' },
        },
        scan: {
          '0%': { transform: 'translateY(-100%)' },
          '50%': { transform: 'translateY(100%)' },
          '100%': { transform: 'translateY(-100%)' },
        },
        glowPulse: {
          '0%, 100%': { opacity: '0.4' },
          '50%': { opacity: '1' },
        },
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'gradient-mesh-dark': 'radial-gradient(at 20% 30%, rgba(0, 229, 255, 0.04) 0px, transparent 50%), radial-gradient(at 80% 20%, rgba(0, 229, 255, 0.03) 0px, transparent 50%), radial-gradient(at 60% 80%, rgba(255, 184, 0, 0.02) 0px, transparent 50%)',
        'grid-pattern': 'linear-gradient(rgba(0, 229, 255, 0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 229, 255, 0.05) 1px, transparent 1px)',
      },
    },
  },
  plugins: [],
}
