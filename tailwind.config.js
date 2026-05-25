/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './rewrz/templates/**/*.html',
    './rewrz/static/js/**/*.js',
  ],
  safelist: [
    'grid-cols-2',
    'grid-cols-3',
    'pr-5',
    'pr-9',
    'pl-5',
    'pl-9',
    'bg-slate-100',
    'text-slate-700',
    'dark:bg-slate-700',
    'dark:text-slate-100',
    'bg-blue-100',
    'text-blue-700',
    'dark:bg-blue-900/40',
    'dark:text-blue-300',
    'bg-purple-100',
    'text-purple-700',
    'dark:bg-purple-900/40',
    'dark:text-purple-300',
    'rounded-xl',
    'bg-gray-50',
    'dark:bg-gray-900/60',
    'border',
    'border-gray-200',
    'dark:border-gray-700',
    'p-4',
    'md:p-5',
    'bg-white/70',
    'border-white/40',
    'dark:border-gray-700/60',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['SourceHanSansCN', 'Microsoft YaHei', 'system-ui', 'sans-serif'],
      },
      colors: {
        primary: {
          50: '#eff6ff',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
        },
      },
      animation: {
        'fade-in-up': 'fadeInUp 0.6s ease-out forwards',
        'slide-in-right': 'slideInRight 0.6s ease-out forwards',
        'slide-in-left': 'slideInLeft 0.6s ease-out forwards',
      },
      keyframes: {
        fadeInUp: {
          '0%': {
            opacity: '0',
            transform: 'translateY(16px)',
          },
          '100%': {
            opacity: '1',
            transform: 'translateY(0)',
          },
        },
        slideInRight: {
          '0%': {
            opacity: '0',
            transform: 'translateX(20px)',
          },
          '100%': {
            opacity: '1',
            transform: 'translateX(0)',
          },
        },
        slideInLeft: {
          '0%': {
            opacity: '0',
            transform: 'translateX(-20px)',
          },
          '100%': {
            opacity: '1',
            transform: 'translateX(0)',
          },
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
    require('@tailwindcss/line-clamp'),
  ],
};
