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

test('T-1001/T-1002: refinement shell composes capability-local views', () => {
	const shell = read('./CanvasRefinementWorkspace.svelte');
	const adjust = read('./RefinementAdjustView.svelte');
	const color = read('./RefinementColorCatalogView.svelte');
	const grid = read('./RefinementCandidateGrid.svelte');
	const models = read('./RefinementModelCompareView.svelte');
	const styles = read('./refinement-workspace.css');
	const panel = read('../../components/CanvasPanel.svelte');

	assert.match(shell, /import RefinementAdjustView/);
	assert.match(shell, /import RefinementModelCompareView/);
	assert.match(shell, /<RefinementAdjustView/);
	assert.match(shell, /<RefinementModelCompareView/);
	assert.match(shell, /<RefinementColorCatalogView/);
	assert.doesNotMatch(shell, /RefinementLanguageCompareView|language/);
	assert.match(adjust, /class="refine-panel"/);
	assert.match(adjust, /<RefinementCandidateGrid/);
	assert.match(color, /<RefinementCandidateGrid/);
	assert.match(grid, /class="variation-grid"/);
	assert.match(adjust, /Same picker and same semantics as DdlEditorDialog/);
	// Each picked model draws both stages; there is no mode that fixes one.
	// Its drawings are options kept with "+", as in the color change.
	assert.match(models, /class="model-choice-grid"/);
	assert.match(models, /<RefinementCandidateGrid/);
	assert.doesNotMatch(models, /compare-mode-tabs|stage1_fixed|stage2_fixed/);
	assert.match(styles, /Fit candidates into the remaining height/);
	assert.doesNotMatch(styles, /:global\(/, 'external CSS must use standard selectors');

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
		'setRefineKind',
		'openLineageRefinement',
		'closeRefineModal',
		'artworkUrl'
	]) {
		assert.match(panel, new RegExp(`\\b${owner}\\b`), `${owner} left CanvasPanel`);
	}
	assert.match(panel, /localStorage\.setItem\(REFINE_KIND_KEY, kind\)/);
	assert.match(panel, /\(statusDdlOrigin \|\| statusDescriptionLocked\) && refineKind === 'reading'/);
	assert.match(panel, /if \(refineModalOpen\) requestCloseRefineModal\(\)/);
	assert.match(panel, /view=\{refineView\}/);
	assert.match(panel, /onClose=\{requestCloseRefineModal\}/);
	assert.doesNotMatch(view, /\$state\(|localStorage|onMount|URL\.createObjectURL/);
});

test('T-1002/T-1005: focused refinement views reuse typed owners without cross-view capabilities', () => {
	const shell = read('./CanvasRefinementWorkspace.svelte');
	const adjust = read('./RefinementAdjustView.svelte');
	const models = read('./RefinementModelCompareView.svelte');
	const color = read('./RefinementColorCatalogView.svelte');
	const grid = read('./RefinementCandidateGrid.svelte');
	const session = read('./refinement-session.svelte.ts');

	assert.match(session, /type RefinementView = 'adjust' \| 'compare' \| 'color'/);
	assert.match(shell, /view: RefinementView/);
	assert.match(shell, /onClose: \(\) => void/);
	assert.match(adjust, /refinementSession: RefinementSession/);
	assert.match(adjust, /onSetRefineKind: \(kind: RefineKind\)/);
	assert.doesNotMatch(adjust, /modelInspection/);
	assert.match(models, /modelInspection: ModelInspection/);
	assert.doesNotMatch(models, /onGenerateVariationCandidates|touchSeedText|LANGUAGE_COMBOS/);
	for (const source of [shell, adjust, models, color, grid]) {
		assert.doesNotMatch(source, /\bany\b|apiFetch|CanvasPanel|\+page|createContext|setContext|getContext/);
		assert.doesNotMatch(source, /\$state\(|localStorage|onMount|URL\.createObjectURL/);
	}
});

test('I-528: language comparison has no Canvas or Lineage entry point', () => {
	const shell = read('./CanvasRefinementWorkspace.svelte');
	const panel = read('../../components/CanvasPanel.svelte');
	const lineage = read('../../components/LineagePanel.svelte');

	for (const source of [shell, panel, lineage]) {
		assert.doesNotMatch(source, /RefinementLanguageCompareView|Change languages|使用言語変更/);
	}
	assert.doesNotMatch(shell, /'language'/);
	assert.doesNotMatch(panel, /'language'/);
	assert.doesNotMatch(lineage, /'language'/);
});
