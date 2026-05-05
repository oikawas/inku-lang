// @ts-nocheck
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import { readFileSync, statSync } from 'fs';
import { fileURLToPath } from 'url';
import { resolve, dirname } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const buildNumberFile = resolve(__dirname, 'BUILD_NUMBER');
const packageFile = resolve(__dirname, 'package.json');

let buildNumber = 1;
try {
	buildNumber = parseInt(readFileSync(buildNumberFile, 'utf-8').trim(), 10);
} catch { /* first run */ }

let buildDate = 'unknown';
try {
	buildDate = statSync(buildNumberFile).mtime.toISOString();
} catch { /* first run */ }

let appVersion = '0.1.0';
try {
	appVersion = JSON.parse(readFileSync(packageFile, 'utf-8')).version ?? appVersion;
} catch { /* first run */ }

function startupBannerPlugin() {
	return {
		name: 'inku-startup-banner',
		configureServer() {
			console.info([
				'==============================',
				'🎨 inku-server starting',
				'service: SvelteKit web UI',
				`version: ${appVersion}`,
				`build: ${buildNumber} (${buildDate})`,
				'=============================='
			].join('\n'));
		}
	};
}

export default defineConfig({
	define: {
		__BUILD_NUMBER__: JSON.stringify(String(buildNumber))
	},
	plugins: [startupBannerPlugin(), sveltekit()],
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
