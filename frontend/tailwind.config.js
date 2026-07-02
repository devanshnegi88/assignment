export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      boxShadow: {
        glass: '0 20px 60px rgba(15, 23, 42, 0.18)',
      },
      backgroundImage: {
        'frosted': 'radial-gradient(circle at top, rgba(59, 130, 246, 0.14), transparent 45%), radial-gradient(circle at bottom right, rgba(168, 85, 247, 0.08), transparent 35%)'
      }
    }
  },
  plugins: [],
};
