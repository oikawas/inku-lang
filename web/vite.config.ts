import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, type Plugin } from 'vite';
// This package intentionally has no @types/node dependency. Keep the Node-only
// Vite boundary explicit instead of disabling type checking for this whole file.
// @ts-expect-error Node built-in types are unavailable in the browser package.
import { readFileSync, statSync } from 'node:fs';
// @ts-expect-error Node built-in types are unavailable in the browser package.
import { fileURLToPath } from 'node:url';
// @ts-expect-error Node built-in types are unavailable in the browser package.
import { resolve, dirname } from 'node:path';

const nodeRuntime = (globalThis as typeof globalThis & {
	process: { version: string; platform: string; arch: string };
}).process;

const __dirname = dirname(fileURLToPath(import.meta.url));
const buildNumberFile = resolve(__dirname, 'BUILD_NUMBER');
const appVersionFile = resolve(__dirname, 'APP_VERSION');

let buildNumber = 1;
try {
	buildNumber = parseInt(readFileSync(buildNumberFile, 'utf-8').trim(), 10);
} catch { /* first run */ }

let buildDate = 'unknown';
try {
	buildDate = statSync(buildNumberFile).mtime.toISOString();
} catch { /* first run */ }

// APP_VERSION is the single source for the application version: this banner, the
// UI (via __APP_VERSION__), the server (/api/info) and the CLI all read this one
// file. package.json carries the npm package version and is deliberately not read
// here -- it is 0.1.0 and names a different thing.
let appVersion = 'unknown';
try {
	appVersion = readFileSync(appVersionFile, 'utf-8').trim() || appVersion;
} catch { /* first run */ }

function startupBannerPlugin(): Plugin {
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
				`runtime: ${nodeRuntime.version} / ${nodeRuntime.platform} ${nodeRuntime.arch}`,
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
		__APP_VERSION__: JSON.stringify(appVersion),
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
