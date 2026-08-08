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
// There is no component renderer here, so this asserts the wiring in the page's
// own words, plus the fallback rule itself. Neither half alone is a gate: assert
// only the rule and the page can stop sending the field; assert only the field
// and it can be sent as `||`, which drops seed 0 through to the fallback.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

const here = path.dirname(new URL(import.meta.url).pathname);
const page = fs.readFileSync(path.join(here, '+page.svelte'), 'utf8');

/** The effective placement seed, as the server resolves it. */
const placementSeed = (compositionSeed: number | null, renderSeed: number | null) =>
	compositionSeed ?? renderSeed ?? null;

function body(fnName: string): string {
	const start = page.indexOf(`async function ${fnName}(`);
	assert.notEqual(start, -1, `${fnName} is gone; this gate names the wrong function`);
	const next = page.indexOf('\n\tasync function ', start + 1);
	return page.slice(start, next === -1 ? page.length : next);
}

test('both touch refinements send the placement seed the picture was drawn with', () => {
	// varyPerformance draws a fresh render_seed; renderWordTouchCandidate derives one
	// from the words. Both are the same button, and both must hold the composition.
	for (const fn of ['varyPerformance', 'renderWordTouchCandidate']) {
		const source = body(fn);
		assert.match(
			source,
			/composition_seed:\s*(?:placementSeed|result\.composition_seed \?\? result\.render_seed)/,
			`${fn} must send the effective placement seed`
		);
		assert.doesNotMatch(
			source,
			/composition_seed:\s*result\.composition_seed\s*\|\|/,
			`${fn} must not use ||, which sends seed 0 to the fallback`
		);
	}
});

test('varyPerformance keeps the placement seed on the result', () => {
	// Without this, the first touch change holds the composition and the second one
	// finds no composition_seed and falls back to the performance seed it just drew.
	const source = body('varyPerformance');
	assert.match(source, /result = \{[^}]*composition_seed: placementSeed/);
});

test('a seed of zero is a seed, not an absent one', () => {
	assert.equal(placementSeed(0, 4242), 0);
	assert.equal(placementSeed(null, 4242), 4242);
	assert.equal(placementSeed(null, 0), 0);
	assert.equal(placementSeed(null, null), null);
});
