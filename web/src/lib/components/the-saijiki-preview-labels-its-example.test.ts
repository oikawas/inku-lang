// Run with: npm run test:unit  (node:test, no test dependency)
//
// A saijiki preview shows the word, what it does, and a fragment of DDL that
// uses it. The fragment had no label, so it could not be told apart from the
// sentence above it (the author, 2026-10-15). Both previews -- the one under
// the DDL editor and the saijiki drawer -- open the example line with a label
// in the UI's language; the example itself stays in the word's language.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { SAIJIKI, SAIJIKI_BUNDLES, bundleLabel, hydrateSaijikiBundles, saijikiGroups } from '../saijiki.ts';

const read = (relative: string) => readFileSync(new URL(relative, import.meta.url), 'utf8');

const PREVIEWS = {
	SaijikiInline: read('./SaijikiInline.svelte'),
	SaijikiDrawer: read('./SaijikiDrawer.svelte'),
};

test('the example line opens with its label in both saijiki previews', () => {
	for (const [name, source] of Object.entries(PREVIEWS)) {
		const lines = [...source.matchAll(/<div class="saijiki-preview-example">([\s\S]*?)<\/div>/g)].map((match) => match[1]);
		assert.equal(lines.length, 1, `${name}: expected one example line`);
		assert.match(
			lines[0],
			/^<span class="saijiki-preview-example-label">\{t\(\)\.saijikiPreviewExampleLabel\}<\/span>\{activePreview\.example\}$/,
			`${name}: the example line does not open with the label`
		);
	}
});

test('the label is written in both UI languages', () => {
	assert.match(read('../i18n/ja.ts'), /\n\tsaijikiPreviewExampleLabel: '例文：',\n/);
	assert.match(read('../i18n/en.ts'), /\n\tsaijikiPreviewExampleLabel: 'Example: ',\n/);
});

test('the bundle names and order follow the server snapshot and hydration', () => {
	const saved = SAIJIKI_BUNDLES.map((bundle) => ({ ...bundle }));
	try {
		assert.deepEqual(saijikiGroups(SAIJIKI).map((group) => group.key), saved.map((bundle) => bundle.key));
		assert.equal(bundleLabel('where', true), saved.find((bundle) => bundle.key === 'where')?.name_ja);
		hydrateSaijikiBundles([{ key: 'where', name_ja: '場所', name_en: 'Place' }]);
		assert.deepEqual(saijikiGroups(SAIJIKI).map((group) => group.key), ['where']);
		assert.equal(bundleLabel('where', false), 'Place');
	} finally {
		hydrateSaijikiBundles(saved);
	}
});
