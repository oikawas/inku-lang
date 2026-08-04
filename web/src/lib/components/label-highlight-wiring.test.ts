// Run with: npm run test:unit  (node:test, no test dependency)
//
// The rule can be perfect and paint nothing.  There is no component renderer
// here (test:unit is node:test with no DOM), so this reads the sources: both
// editors must hand their own text to the layer, and the textarea above it must
// be transparent or the layer is painted behind an opaque box.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

const here = path.dirname(new URL(import.meta.url).pathname);
const read = (name: string) => fs.readFileSync(path.join(here, name), 'utf8');

test('the describe tab paints its own text', () => {
	const source = read('InputPanel.svelte');
	assert.match(source, /<LabelHighlight text=\{input\}/);
	assert.match(source, /import LabelHighlight from '\.\/LabelHighlight\.svelte'/);
});

test('the batch tab paints its own text, and does not wrap', () => {
	const source = read('BatchPanel.svelte');
	assert.match(source, /<LabelHighlight text=\{batchInput\} wrap=\{false\}/);
	// It scrolls sideways, so the layer has to follow both offsets.
	assert.match(source, /scrollTop=\{batchScrollTop\} scrollLeft=\{batchScrollLeft\}/);
	assert.match(source, /batchScrollLeft = batchTextareaEl\?\.scrollLeft/);
});

test('both textareas are transparent, so the layer below them is visible', () => {
	for (const name of ['InputPanel.svelte', 'BatchPanel.svelte']) {
		const source = read(name);
		const rule = source.slice(source.indexOf(name === 'BatchPanel.svelte' ? '.batch-ta {' : '.input-ta {'));
		const body = rule.slice(0, rule.indexOf('}'));
		assert.match(body, /background:\s*transparent/, `${name} hides the layer`);
	}
});

test('the layer matches the textareas it sits behind', () => {
	const layer = read('LabelHighlight.svelte');
	// Same padding, size and line-height as both editors: a mismatch shifts the
	// grey away from the characters it belongs to.
	for (const metric of [/padding:\s*9px 10px/, /font-size:\s*13px/, /line-height:\s*1\.65/]) {
		assert.match(layer, metric);
	}
	for (const name of ['InputPanel.svelte', 'BatchPanel.svelte']) {
		const source = read(name);
		assert.match(source, /padding:\s*9px 10px/, name);
		assert.match(source, /font-size:\s*13px;\s*line-height:\s*1\.65/, name);
	}
});
