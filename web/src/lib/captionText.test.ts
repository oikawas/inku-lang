// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

import { captionParts } from './captionText.ts';

const emphasized = (text: string) => captionParts(text).filter((part) => part.italic).map((part) => part.text);
const here = path.dirname(new URL(import.meta.url).pathname);
const read = (relative: string) => fs.readFileSync(path.join(here, relative), 'utf8');

test('square-bracket comments are italic including their brackets', () => {
	const text = '霧[季節の補足]と［作者のメモ］';
	const parts = captionParts(text);
	assert.equal(parts.map((part) => part.text).join(''), text);
	assert.deepEqual(emphasized(text), ['[季節の補足]', '［作者のメモ］']);
});

test('an unclosed bracket remains ordinary text', () => {
	assert.deepEqual(captionParts('霧[未完'), [{ text: '霧[未完', italic: false }]);
});

test('the complete refinement-direction line is italic in both languages', () => {
	const text = '霧[補足]\n推敲方針: 青を強く\nRefinement direction: quieter';
	const parts = captionParts(text);
	assert.equal(parts.map((part) => part.text).join(''), text);
	assert.deepEqual(emphasized(text), ['[補足]', '推敲方針: 青を強く', 'Refinement direction: quieter']);
});

test('the normal canvas and presentation render headnotes through the same formatter', () => {
	for (const source of [
		read('./features/canvas/CanvasArtworkWorkspace.svelte'),
		read('./features/canvas/CanvasPresentationOverlay.svelte')
	]) {
		assert.match(source, /<CaptionText text=\{displayInstructionText\} \/>/);
	}
});
