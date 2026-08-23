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

test('T-334: generation information has one feature-local focused view', () => {
	const view = read('./CanvasGenerationInfo.svelte');
	const panel = read('../../components/CanvasPanel.svelte');

	assert.match(view, /<aside[\s\S]*class="generation-info"/);
	assert.match(view, /<OutputTabsContent/);
	assert.match(view, /detailSketchState/);
	assert.match(view, /class="generation-details"/);
	assert.match(view, /\.generation-info \{/);

	assert.match(panel, /import CanvasGenerationInfo from '\$lib\/features\/canvas\/CanvasGenerationInfo\.svelte'/);
	assert.match(panel, /<CanvasGenerationInfo/);
	assert.doesNotMatch(panel, /<aside[\s\S]{0,300}class="generation-info"/);
	assert.doesNotMatch(panel, /const detailSketchState/);
	assert.doesNotMatch(panel, /\.generation-details \{/);
});

test('T-335/T-337: CanvasPanel keeps coordination and lends shared derivations', () => {
	const view = read('./CanvasGenerationInfo.svelte');
	const panel = read('../../components/CanvasPanel.svelte');

	for (const owner of [
		'generationInfoOpen',
		'generationInfoTab',
		'closeGenerationInfo',
		'openGenerationInfo',
		'drawerScrollMemory',
		'drawerScroller'
	]) {
		assert.match(panel, new RegExp(`\\b${owner}\\b`), `${owner} left CanvasPanel`);
	}
	assert.match(panel, /const detailSvgWeight = \$derived/);
	assert.match(panel, /detailSvgWeight=\{detailSvgWeight\}/);
	assert.match(panel, /bind:drawerEl=\{generationInfoEl\}/);
	assert.match(panel, /bind:detailsScrollEl/);
	assert.match(panel, /bind:tabsScrollEl/);
	assert.match(view, /bind:this=\{drawerEl\}/);
	assert.match(view, /bind:this=\{detailsScrollEl\}/);
	assert.match(view, /bind:scrollEl=\{tabsScrollEl\}/);
	assert.equal((view.match(/<OutputTabsContent/g) ?? []).length, 1);
	assert.doesNotMatch(panel, /<OutputTabsContent/);
});

test('T-338: the focused view is typed and owns no route or session state', () => {
	const view = read('./CanvasGenerationInfo.svelte');

	assert.match(view, /type Props = \{/);
	assert.doesNotMatch(view, /\bany\b/);
	assert.doesNotMatch(view, /\$state\(/);
	assert.doesNotMatch(view, /apiFetch|createContext|setContext|getContext/);
	assert.doesNotMatch(view, /CanvasPanel|\+page/);
});
