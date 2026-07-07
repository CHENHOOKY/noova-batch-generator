export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      fontFamily: { sans: ['"Microsoft YaHei"', 'PingFang SC', 'system-ui', 'sans-serif'] },
      colors: { brand: { DEFAULT: '#6366F1', dark: '#4F46E5', soft: '#EEF2FF' } }
    }
  },
  plugins: []
}
