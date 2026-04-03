/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          base:   '#111827',
          panel:  '#1a2035',
          card:   '#1f2937',
          hover:  '#253047',
          border: '#2d3748',
          muted:  '#374151',
        },
        entity: {
          person:       '#818cf8',
          concept:      '#a78bfa',
          place:        '#34d399',
          work:         '#fbbf24',
          organization: '#60a5fa',
          other:        '#9ca3af',
        },
        accent: {
          primary:  '#6366f1',
          hover:    '#4f46e5',
          muted:    '#312e81',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      fontSize: {
        'caption': ['11px', '16px'],
        'body':    ['13px', '20px'],
        'label':   ['14px', '20px'],
        'heading': ['16px', '24px'],
      }
    }
  },
  plugins: []
}