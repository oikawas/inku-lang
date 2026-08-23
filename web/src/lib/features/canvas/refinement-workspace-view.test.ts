import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (path: string): string => {
	try { return readFileSync(join(HERE, path), 'utf8'); }
	catch { return ''; }
};

test('T-345: refinement workspace has one feature-local focused view', () => {
	const view = read('./CanvasRefinementWorkspace.svelte');
	const panel = read('../../components/CanvasPanel.svelte');

	assert.match(view, /class="refine-shell"/);
	assert.match(view, /class="refine-panel"/);
	assert.match(view, /class="compare-panel"/);
	assert.match(view, /class="variation-grid"/);
	assert.match(view, /\.refine-shell \{/);
	assert.match(view, /\.compare-panel \{/);
	assert.match(view, /Same picker and same semantics as DdlEditorDialog/);
	assert.match(view, /Fit candidates into the remaining height/);

	assert.match(panel, /import CanvasRefinementWorkspace from '\$lib\/features\/canvas\/CanvasRefinementWorkspace\.svelte'/);
	assert.match(panel, /<CanvasRefinementWorkspace/);
	assert.doesNotMatch(panel, /class="refine-shell"/);
	assert.doesNotMatch(panel, /\.refine-shell \{/);
	assert.doesNotMatch(panel, /\.compare-panel \{/);
});

test('T-346: CanvasPanel keeps refinement view coordination and local choices', () => {
	const view = read('./CanvasRefinementWorkspace.svelte');
	const panel = read('../../components/CanvasPanel.svelte');

	for (const owner of [
		'refineView',
		'refineModalOpen',
		'refineKind',
		'variationAmplitude',
		'setRefineKind',
		'openLineageRefinement',
		'closeRefineModal',
		'artworkUrl'
	]) {
		assert.match(panel, new RegExp(`\\b${owner}\\b`), `${owner} left CanvasPanel`);
	}
	assert.match(panel, /localStorage\.setItem\(REFINE_KIND_KEY, kind\)/);
	assert.match(panel, /statusDdlOrigin && refineKind === 'reading'/);
	assert.match(panel, /if \(refineModalOpen\) closeRefineModal\(\)/);
	assert.match(panel, /view=\{refineView\}/);
	assert.match(panel, /onClose=\{closeRefineModal\}/);
	assert.doesNotMatch(view, /\$state\(|localStorage|onMount|URL\.createObjectURL/);
});

test('T-347/T-348: all three views use the existing typed owners and narrow callbacks', () => {
	const view = read('./CanvasRefinementWorkspace.svelte');

	assert.match(view, /type Props = \{/);
	assert.match(view, /refinementSession: RefinementSession/);
	assert.match(view, /modelInspection: ModelInspection/);
	assert.match(view, /type RefinementView = 'adjust' \| 'compare' \| 'language'/);
	assert.match(view, /view: RefinementView/);
	assert.match(view, /onSetRefineKind: \(kind: RefineKind\)/);
	assert.match(view, /onClose: \(\) => void/);
	assert.match(view, /width: min\(1120px, calc\(100% - 136px\)\)/);
	assert.doesNotMatch(view, /\bany\b|apiFetch|CanvasPanel|\+page|createContext|setContext|getContext/);

	const adjust = view.indexOf("view === 'adjust'");
	const compare = view.indexOf("view === 'compare'");
	const language = view.indexOf('LANGUAGE_COMBOS');
	assert.ok(adjust >= 0 && compare > adjust && language >= 0, 'the three workspace views are incomplete');
});
