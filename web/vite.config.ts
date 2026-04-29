// @ts-nocheck
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { resolve, dirname } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const buildNumberFile = resolve(__dirname, 'BUILD_NUMBER');

let buildNumber = 1;
try {
	buildNumber = parseInt(readFileSync(buildNumberFile, 'utf-8').trim(), 10);
} catch { /* first run */ }

export default defineConfig({
	define: {
		__BUILD_NUMBER__: JSON.stringify(String(buildNumber))
	},
	plugins: [sveltekit()],
	server: {
		host: '0.0.0.0',
		port: 5173,
		proxy: {
			'/api': {
				target: 'http://127.0.0.1:8100',
				changeOrigin: false
			}
		}
	}
});
