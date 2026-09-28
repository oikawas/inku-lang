// Run with: npm run test:unit  (node:test, no test dependency)
//
// `Another performance` promises "Same interpretation, same composition — only the
// performance sways" (tooltipCanvasVaryPerformance). Until render engine 23 that
// promise could not be kept: one seed decided both the placement and the hand.
//
// The engine separated them, but the promise is only kept if the page sends the
// placement seed the picture on screen was actually drawn with. The server reads
//
//     placement_seed = composition_seed if composition_seed is not None else render_seed
//                                                            (renderer.py:3058)
//
// so the effective placement seed of the displayed work is `composition_seed ??
// render_seed`. Sending the raw `composition_seed` is not enough: it is null for
// every work that never asked for one, and the placement would then follow the
// new performance seed — exactly the defect engine 23 set out to end.
//
// There is no component renderer here, so this asserts the word-touch candidate's
// request, plus the fallback rule itself.
//
// ⚠ Only the request body is read. A first version of this file matched anywhere
// in the function, so the result line alone satisfied it and dropping the field
// from the request body stayed green.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

const here = path.dirname(new URL(import.meta.url).pathname);
const coordinator = fs.readFileSync(path.join(here, '../lib/features/canvas/refinement-coordinator.svelte.ts'), 'utf8');

/** The effective placement seed, as the server resolves it. */
const placementSeed = (compositionSeed: number | null, renderSeed: number | null) =>
	compositionSeed ?? renderSeed ?? null;

function body(source: string, fnName: string): string {
	const start = source.indexOf(`function ${fnName}(`);
	assert.notEqual(start, -1, `${fnName} is gone; this gate names the wrong function`);
	const markers = ['\n\tasync function ', '\n\tfunction '];
	const next = markers
		.map((marker) => source.indexOf(marker, start + 1))
		.filter((index) => index !== -1)
		.sort((left, right) => left - right)[0] ?? -1;
	return source.slice(start, next === -1 ? source.length : next);
}

/** What the function sends: everything from the request literal to the response check. */
function request(sourceText: string, fnName: string): string {
	const source = body(sourceText, fnName);
	const from = source.indexOf('JSON.stringify({');
	const to = source.indexOf('if (!', from);
	assert.ok(from !== -1 && to > from, `${fnName} no longer builds a request this way`);
	return source.slice(from, to);
}

test('the touch candidate sends the placement seed the picture was drawn with', () => {
	// The candidate derives its performance seed from words; it must hold the composition.
	assert.match(
		request(coordinator, 'renderWordTouchCandidate'),
		/composition_seed:\s*work\.result\.composition_seed \?\? work\.result\.render_seed/,
		'renderWordTouchCandidate must send the effective placement seed'
	);
});

test('the fallback is written with ??, so a seed of zero is not dropped', () => {
	// `||` would send render_seed for a work whose composition_seed is 0 — the one
	// user who asked for seed 0 is the one who would not get their composition back.
	for (const fn of ['renderWordTouchCandidate']) {
		const source = body(coordinator, fn);
		assert.doesNotMatch(source, /composition_seed\s*\|\|/, `${fn} must not fall back with ||`);
		assert.match(
			source,
			/work\.result\.composition_seed \?\? work\.result\.render_seed/,
			`${fn} must resolve the placement seed the way the server does`
		);
	}
});

test('a seed of zero is a seed, not an absent one', () => {
	assert.equal(placementSeed(0, 4242), 0);
	assert.equal(placementSeed(null, 4242), 4242);
	assert.equal(placementSeed(null, 0), 0);
	assert.equal(placementSeed(null, null), null);
});
