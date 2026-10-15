import { defineConfig } from 'vite';
import dts from 'vite-plugin-dts';
import { vanillaExtractPlugin } from '@vanilla-extract/vite-plugin';
import { resolve } from 'path';

export default defineConfig({
  plugins: [
    vanillaExtractPlugin(),
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
      external: ['react', 'react-dom', 'preact'],
      output: {
        globals: {
          react: 'React',
          'react-dom': 'ReactDOM',
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