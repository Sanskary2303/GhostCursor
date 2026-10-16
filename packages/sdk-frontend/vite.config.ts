import { defineConfig } from 'vite';
import dts from 'vite-plugin-dts';
import { resolve } from 'path';

export default defineConfig({
  plugins: [
    dts({
      insertTypesEntry: true,
      outDir: 'dist',
      tsconfigPath: './tsconfig.json',
    }),
  ],
  build: {
    lib: {
      entry: resolve(__dirname, 'src/index.ts'),
      name: 'GhostCursorSDK',
      fileName: (format) => `ghost-cursor.${format}.js`,
      formats: ['es', 'umd'],
    },
    rollupOptions: {
      external: ['preact'],
      output: {
        globals: {
          preact: 'preact',
        },
      },
    },
    outDir: 'dist',
    sourcemap: true,
    minify: 'esbuild',
    target: 'es2022',
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  define: {
    'process.env.NODE_ENV': '"production"',
  },
});