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

test('T-340: presentation has one feature-local focused view', () => {
	const view = read('./CanvasPresentationOverlay.svelte');
	const panel = read('../../components/CanvasPanel.svelte');

	assert.match(view, /class="presentation-overlay"/);
	assert.match(view, /class="presentation-controls"/);
	assert.match(view, /\.presentation-overlay \{/);
	assert.match(view, /The same work as the canvas, shown larger/);
	assert.match(panel, /import CanvasPresentationOverlay from '\$lib\/features\/canvas\/CanvasPresentationOverlay\.svelte'/);
	assert.match(panel, /<CanvasPresentationOverlay/);
	assert.doesNotMatch(panel, /<div class="presentation-overlay"/);
	assert.doesNotMatch(panel, /\.presentation-overlay \{/);
});

test('T-341: CanvasPanel keeps presentation coordination and mutations', () => {
	const view = read('./CanvasPresentationOverlay.svelte');
	const panel = read('../../components/CanvasPanel.svelte');

	assert.match(panel, /let presentationMode = \$state\(false\)/);
	assert.match(panel, /function closePresentationMode\(\)/);
	assert.match(panel, /else if \(presentationMode\) closePresentationMode\(\)/);
	assert.match(panel, /presentationMode = true/);
	assert.match(panel, /\{#if presentationMode && result\}[\s\S]*<CanvasPresentationOverlay/);
	for (const callback of ['onGotoNext', 'onGotoLatest', 'onGotoPrev', 'onToggleStar', 'toggleInstructionCaption', 'closePresentationMode']) {
		assert.match(panel, new RegExp(`\\b${callback}\\b`), `${callback} left CanvasPanel`);
	}
	assert.doesNotMatch(view, /\$state\(|presentationMode|apiFetch|createContext|setContext|getContext/);
});

test('T-342/T-343: controls keep their order and use a typed narrow interface', () => {
	const view = read('./CanvasPresentationOverlay.svelte');
	const controls = view.slice(view.indexOf('class="presentation-controls"'));
	const positions = ['onGotoNext', 'onGotoLatest', 'onGotoPrev', 'onToggleStar', 'onToggleCaption', 'onClose']
		.map((name) => controls.indexOf(name));
	assert.ok(positions.every((position) => position >= 0), `missing control: ${positions}`);
	for (let index = 1; index < positions.length; index += 1) {
		assert.ok(positions[index - 1] < positions[index], `control order changed at ${index}`);
	}
	assert.match(view, /type Props = \{/);
	assert.match(view, /type PresentationWorkMark = \{/);
	assert.doesNotMatch(view, /\bany\b|CanvasPanel|\+page|generic|controller/);
	assert.match(view, /@media \(max-width: 720px\)/);
});
