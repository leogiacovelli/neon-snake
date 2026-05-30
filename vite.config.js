import { defineConfig } from 'vite';

// Relative base so the production build works under any sub-path
// (GitHub Pages project sites, itch.io, S3 sub-folders, etc.).
export default defineConfig({
  base: './',
  build: {
    target: 'es2020',
    cssCodeSplit: false,
    assetsInlineLimit: 4096,
  },
  server: {
    host: true,
    open: true,
  },
});
