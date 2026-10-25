// A lineage card fell through to "Deleted work" whenever a work's text was
// empty, so a picture-drawn work with no source note read as deleted
// (de5882f9, 2026-10-25). Only a node without its work is withheld now.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { ja } from './i18n/ja';

const panel = readFileSync(new URL('./components/LineagePanel.svelte', import.meta.url), 'utf8');
const body = panel.slice(panel.indexOf('function workText'), panel.indexOf('}', panel.indexOf('return history.source_text', panel.indexOf('function workText'))) + 1);

// The function as written, run against the cases.
const workText = new Function('t', 'withheldWorkLabel', `return (${body.replace(/^function workText\(node: LineageNode\): string/, 'function (node)')})`)(
	() => ja, () => '削除された作品'
) as (node: unknown) => string;

test('a present work is never called deleted', () => {
	assert.equal(workText({ history: { image_ddl: {}, image_provenance: '', source_text: '', input: '' } }), ja.lineageImageWork);
	assert.equal(workText({ history: { image_ddl: {}, image_provenance: '鴨川で撮影', input: '' } }), '鴨川で撮影');
	assert.equal(workText({ history: { source_text: '', input: '' } }), ja.lineageNoDescription);
	assert.equal(workText({ history: { source_text: '山の月', input: 'x' } }), '山の月');
	assert.equal(workText({ history: null }), '削除された作品');
});

test('every place the card names its work goes through workText', () => {
	assert.doesNotMatch(panel, /node\.history\?\.source_text \|\| node\.history\?\.input \|\| withheldWorkLabel/);
	assert.equal((panel.match(/workText\(node\)/g) ?? []).length >= 3, true);
});
