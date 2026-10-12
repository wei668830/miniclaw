import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 渲染进程构建配置。
// base: './' 保证 Electron 以 file:// 加载 dist/index.html 时资源路径正确。
export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    strictPort: true,
  },
});
