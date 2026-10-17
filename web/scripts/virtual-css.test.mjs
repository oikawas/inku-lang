import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { createServer } from 'vite';

test('a cold CanvasPanel style request returns scoped CSS before the component loads', async () => {
	const root = fileURLToPath(new URL('../', import.meta.url));
	const previousCwd = process.cwd();
	process.chdir(root); // SvelteKit resolves its config against the working directory.
	let server;
	try {
		server = await createServer({
			root,
			server: { middlewareMode: true, watch: null, hmr: false, ws: false },
			logLevel: 'silent'
		});
		const cssId = `${root}src/lib/components/CanvasPanel.svelte?svelte&type=style&lang.css`;
		for (let request = 0; request < 2; request++) {
			const result = await server.transformRequest(cssId);
			assert.ok(result);
			assert.doesNotMatch(result.code, /<script lang=/);
			assert.match(result.code, /\.right-panel\.svelte-/);
			assert.match(result.code, /display: flex/);
		}
	} finally {
		await server?.close();
		process.chdir(previousCwd);
	}
});
