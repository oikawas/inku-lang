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
			const border = '='.repeat(60);
			const host = '0.0.0.0';
			const port = 5173;
			console.info([
				border,
				'🎨 🖼️ 🌈 🪄 ✨ inku-server starting 🚀',
				'service: SvelteKit web UI',
				'mode: development',
				`listen: ${host}:${port}`,
				`runtime: ${process.version} / ${process.platform} ${process.arch}`,
				'log: journal + /var/log/inku/inku-server.log',
				`version: ${appVersion}`,
				`build: ${buildNumber} (${buildDate})`,
				border
			].join('\n'));
		}
	};
}

export default defineConfig({
	define: {
		__BUILD_NUMBER__: JSON.stringify(String(buildNumber)),
		// The build date is the mtime of BUILD_NUMBER, the same source the server
		// banner reads (api.py:_build_date). A fresh clone stamps its own mtime.
		__BUILD_DATE__: JSON.stringify(buildDate)
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
