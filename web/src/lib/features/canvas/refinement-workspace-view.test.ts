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

test('T-1001/T-1002: refinement shell composes three capability-local views', () => {
	const shell = read('./CanvasRefinementWorkspace.svelte');
	const adjust = read('./RefinementAdjustView.svelte');
	const models = read('./RefinementModelCompareView.svelte');
	const languages = read('./RefinementLanguageCompareView.svelte');
	const styles = read('./refinement-workspace.css');
	const panel = read('../../components/CanvasPanel.svelte');

	assert.match(shell, /import RefinementAdjustView/);
	assert.match(shell, /import RefinementModelCompareView/);
	assert.match(shell, /import RefinementLanguageCompareView/);
	assert.match(shell, /<RefinementAdjustView/);
	assert.match(shell, /<RefinementModelCompareView/);
	assert.match(shell, /<RefinementLanguageCompareView/);
	assert.match(adjust, /class="refine-panel"/);
	assert.match(adjust, /class="variation-grid"/);
	assert.match(adjust, /Same picker and same semantics as DdlEditorDialog/);
	assert.match(models, /class="compare-mode-tabs"/);
	assert.match(languages, /LANGUAGE_COMBOS/);
	assert.match(styles, /Fit candidates into the remaining height/);

	assert.match(panel, /import CanvasRefinementWorkspace from '\$lib\/features\/canvas\/CanvasRefinementWorkspace\.svelte'/);
	assert.match(panel, /<CanvasRefinementWorkspace/);
	assert.doesNotMatch(panel, /class="refine-shell"/);
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

test('T-1002/T-1005: focused refinement views reuse typed owners without cross-view capabilities', () => {
	const shell = read('./CanvasRefinementWorkspace.svelte');
	const adjust = read('./RefinementAdjustView.svelte');
	const models = read('./RefinementModelCompareView.svelte');
	const languages = read('./RefinementLanguageCompareView.svelte');

	assert.match(shell, /type RefinementView = 'adjust' \| 'compare' \| 'language'/);
	assert.match(shell, /view: RefinementView/);
	assert.match(shell, /onClose: \(\) => void/);
	assert.match(adjust, /refinementSession: RefinementSession/);
	assert.match(adjust, /onSetRefineKind: \(kind: RefineKind\)/);
	assert.doesNotMatch(adjust, /modelInspection/);
	assert.match(models, /modelInspection: ModelInspection/);
	assert.doesNotMatch(models, /onGenerateVariationCandidates|touchSeedText|LANGUAGE_COMBOS/);
	assert.match(languages, /modelInspection: ModelInspection/);
	assert.doesNotMatch(languages, /onGenerateVariationCandidates|touchSeedText|compareMode/);
	for (const source of [shell, adjust, models, languages]) {
		assert.doesNotMatch(source, /\bany\b|apiFetch|CanvasPanel|\+page|createContext|setContext|getContext/);
		assert.doesNotMatch(source, /\$state\(|localStorage|onMount|URL\.createObjectURL/);
	}
});
