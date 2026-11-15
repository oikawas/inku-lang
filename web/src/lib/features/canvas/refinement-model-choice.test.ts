import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');

test('each refinement window initializes and sends its own model', () => {
	const edit = read('../../components/WorkEditDialog.svelte');
	const composition = read('./RefinementCompositionView.svelte');
	const page = read('../../../routes/+page.svelte');
	for (const source of [edit, composition]) {
		assert.match(source, /selectedModel = refinementInitialModel\(\)/);
		assert.match(source, /bind:model=\{selectedModel\}/);
	}
	assert.match(page, /refinementInitialModel=\{\(\) => work\.tabModelRef\('stage1'\)\}/);
	assert.match(edit, /onDrawDescription\(node, draft, controller\.signal, wildOverride, selectedModel\)/);
	assert.match(edit, /onDrawSketchGrain\(node, sketchMode, controller\.signal, wildOverride, selectedModel\)/);
	for (const name of ['drawLineageDescriptionEdit', 'drawLineageSketchGrain']) {
		const start = page.indexOf(`async function ${name}(`);
		const end = page.indexOf('\n}', start);
		assert.ok(start >= 0 && end > start);
		assert.match(page.slice(start, end), /stage1Model: model, stage2Model: model/);
	}
});

test('refinement confirmation restores settings and never persists drawing choices', () => {
	const page = read('../../../routes/+page.svelte');
	const start = page.indexOf('async function confirmModelSelection()');
	const end = page.indexOf('if (modelSelectionForDrawing)', start);
	const refinement = page.slice(start, end);
	assert.match(refinement, /acceptRefinementModel\(qualifiedModelRef\(stage1Provider, stage1Model\)\)/);
	assert.match(refinement, /restoreModelSelection\(\)/);
	assert.doesNotMatch(refinement, /drawOptions|persistModelSelection|invalidateWorkOptions/);
	const opener = page.slice(page.indexOf('function openRefinementModelSelection('), page.indexOf('async function persistModelSelection()'));
	assert.ok(opener.indexOf('splitModelReference(current') < opener.indexOf('openModelSelection(false'));
	assert.match(page, /if \(!refinementModelSelection && Object\.keys\(userModels\)\.length > 0\)/);
	assert.match(page, /if \(!refinementModelSelection && stage1Provider/);
	const settings = read('../../components/SettingsModal.svelte');
	assert.match(settings, /topLayerDialog\?\.showModal\(\)/);
	assert.match(settings, /oncancel=\{\(event\) => \{ event\.preventDefault\(\); onClose\(\); \}\}/);
});
