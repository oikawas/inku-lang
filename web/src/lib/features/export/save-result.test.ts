import assert from 'node:assert/strict';
import { test } from 'node:test';
import { exportFallbackReason } from './save-result.ts';
import type { SaveOutcome } from './save-target.ts';

test('only a denied or failed configured-folder save needs a fallback notice', () => {
	assert.equal(exportFallbackReason({ kind: 'browser', reason: 'denied' }), 'denied');
	assert.equal(exportFallbackReason({ kind: 'browser', reason: 'failed' }), 'failed');
	for (const outcome of [
		{ kind: 'folder', folderName: 'Exports' },
		...(['disabled', 'unsupported', 'no-folder'] as const).map((reason) => ({ kind: 'browser' as const, reason })),
	] satisfies SaveOutcome[]) assert.equal(exportFallbackReason(outcome), null);
	assert.equal(exportFallbackReason(undefined), null);
});

test('contact-sheet notices retain a fallback when later files use the folder', () => {
	assert.equal(exportFallbackReason([
		{ kind: 'browser', reason: 'denied' },
		{ kind: 'folder', folderName: 'Exports' },
	]), 'denied');
	assert.equal(exportFallbackReason([
		{ kind: 'browser', reason: 'failed' },
		{ kind: 'browser', reason: 'denied' },
	]), 'failed');
});
