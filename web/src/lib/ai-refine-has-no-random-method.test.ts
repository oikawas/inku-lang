// Run with: npm run test:unit  (node:test, no test dependency)
//
// Random automatic refinement was removed (the author, 2026-10-18): it drew the
// element of each generation by a die, and the author does not want a feature
// that rolls dice on its own. Vision is the only method until the refinement is
// rebuilt (internal topics/server-task/ai-automation/PLAN.ja.md).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const MODAL = readFileSync(new URL('./components/AIRefineModal.svelte', import.meta.url), 'utf-8');
const JA = readFileSync(new URL('./i18n/ja.ts', import.meta.url), 'utf-8');
const EN = readFileSync(new URL('./i18n/en.ts', import.meta.url), 'utf-8');
const TYPES = readFileSync(new URL('./i18n/types.ts', import.meta.url), 'utf-8');

test('the dialog offers no method to choose', () => {
	assert.doesNotMatch(MODAL, /name="ai-refine-mode"/);
	assert.doesNotMatch(MODAL, /refineMode|RefineMode/);
	assert.match(MODAL, /<p class="method-note">\{t\(\)\.aiRefineVisionModeHint\}<\/p>/);
	for (const copy of [JA, EN, TYPES]) {
		assert.doesNotMatch(copy, /\baiRefineModeLabel:|\baiRefineRandomMode:|\baiRefineRandomModeHint:|\baiRefineVisionMode:/);
	}
});

test("each generation's element is the one Vision names, never a die", () => {
	assert.match(MODAL, /let kind = advice\?\.suggested_kind \?\? activeKinds\[0\];/);
	assert.doesNotMatch(MODAL, /activeKinds\[Math\.floor\(Math\.random\(\)/);
	// Vision reads the work before the first generation and after every one.
	assert.match(MODAL, /\n\s*advice = await readVisionAdvice\(node\.history!\.id!, visionInstruction\(\)\);/);
	assert.match(MODAL, /if \(result\.history_id\) advice = await readVisionAdvice\(result\.history_id, visionInstruction\(\)\);/);
	assert.match(MODAL, /autonomous_refine_mode: 'vision',/);
});

test('a work drawn straight from DDL shows Vision its instructions, not an empty text', () => {
	// The server refuses an empty instruction (min_length 1); macOS already sends the DDL.
	assert.match(MODAL, /const visionInstruction = \(\) => currentText \|\| parent\.ddl;/);
	// The layout generation still receives the description as it was.
	assert.match(MODAL, /result = await onComposeLayout\(parent, currentText, options\);/);
});
