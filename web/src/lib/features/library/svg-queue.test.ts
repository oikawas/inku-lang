import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { SvgQueue } from './svg-queue.ts';

test('thumbnail SVG requests use at most four slots and skip cancelled waiters', async () => {
	let active = 0, peak = 0;
	const release: (() => void)[] = [];
	const queue = new SvgQueue(async () => {
		active++; peak = Math.max(peak, active);
		await new Promise<void>((resolve) => release.push(resolve));
		active--;
		return new Response('<svg/>');
	});
	const controllers = Array.from({ length: 7 }, () => new AbortController());
	const results = controllers.map((controller) => queue.load('/svg', controller.signal));
	controllers[4].abort();
	assert.equal(active, 4);
	while (release.length) {
		release.shift()?.();
		await new Promise((resolve) => setTimeout(resolve, 0));
	}
	assert.equal((await Promise.all(results))[4], '');
	assert.equal(peak, 4);
});

test('thumbnail fallback is reset when its work id or render hash changes', () => {
	const source = readFileSync(new URL('../../components/HistoryThumbnail.svelte', import.meta.url), 'utf8');
	assert.match(source, /\$effect\(\(\) => \{\s*item\.id; item\.render_hash;\s*thumbMissing = false;\s*fetchedSvg = '';/);
});
