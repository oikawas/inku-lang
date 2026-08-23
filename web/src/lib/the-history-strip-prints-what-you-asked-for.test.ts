// Run with: npm run test:unit  (node:test, no test dependency)
//
// The history strip used to print the generation and the Stage 1 model, fixed.
// Four facts are on offer now, at most two at a time, and none is an answer.
//
// The load-bearing distinction is between an absent value and an empty list. An
// account that predates the column has never answered and takes the default; a
// reader who unticked all four has answered, and the answer is "nothing". Read
// through one falsy test the two become the same, and "show nothing" turns into
// a setting that cannot be saved -- it would come back as the default on every
// reload, and no test that only checks the happy path would notice.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import {
	canAddHistoryStripField,
	DEFAULT_HISTORY_STRIP_FIELDS,
	HISTORY_STRIP_FIELD_LIMIT,
	HISTORY_STRIP_FIELDS,
	normalizeHistoryStripFields,
	toggleHistoryStripField,
	type HistoryStripField
} from './historyStripFields.ts';

const STRIP = readFileSync(new URL('./components/HistoryStrip.svelte', import.meta.url), 'utf-8');
const PANEL = readFileSync(new URL('./features/settings/AppearanceSettings.svelte', import.meta.url), 'utf-8');
const JA = readFileSync(new URL('./i18n/ja.ts', import.meta.url), 'utf-8');
const EN = readFileSync(new URL('./i18n/en.ts', import.meta.url), 'utf-8');

test('T-147  an absent value takes the default and an empty list does not', () => {
	// The four shapes an absent value arrives in.
	for (const absent of [undefined, null, {}, 'generation']) {
		assert.deepEqual(normalizeHistoryStripFields(absent), DEFAULT_HISTORY_STRIP_FIELDS);
	}
	// The one shape that means "nothing under the picture".
	assert.deepEqual(normalizeHistoryStripFields([]), []);
	// And the default is what the strip printed before it could be asked, so
	// nobody's strip moves on the day the column appears.
	assert.deepEqual(DEFAULT_HISTORY_STRIP_FIELDS, ['generation', 'model']);
});

test('T-148  at most two survive, in the order the four are declared', () => {
	assert.deepEqual(normalizeHistoryStripFields(['bytes', 'generation']), ['generation', 'bytes']);
	assert.deepEqual(normalizeHistoryStripFields(['bytes', 'bytes']), ['bytes']);
	assert.deepEqual(normalizeHistoryStripFields(['nope', 'bytes']), ['bytes']);
	const three = normalizeHistoryStripFields(['generation', 'model', 'bytes']);
	assert.equal(three.length, HISTORY_STRIP_FIELD_LIMIT);
});

test('T-149  a third tick is refused rather than evicting one of the two', () => {
	const two: HistoryStripField[] = ['generation', 'model'];
	assert.equal(canAddHistoryStripField(two), false);
	// The refusal keeps both -- an eviction would silently move a choice the
	// reader made, and they would find out by reading the strip.
	assert.deepEqual(toggleHistoryStripField(two, 'bytes'), two);
	// Unticking always works, and then the fourth fits.
	const one = toggleHistoryStripField(two, 'model');
	assert.deepEqual(one, ['generation']);
	assert.equal(canAddHistoryStripField(one), true);
	assert.deepEqual(toggleHistoryStripField(one, 'bytes'), ['generation', 'bytes']);
});

test('T-150  the strip prints no meta row at all when nothing was chosen', () => {
	// An empty row still takes its height. The guard has to be on the row, not
	// on the spans inside it.
	assert.match(STRIP, /\{#if historyStripFields\.length > 0\}\s*<div class="thumb-meta">/);
});

test('T-151  the panel offers exactly the four, and each one is named in both languages', () => {
	assert.match(PANEL, /\{#each HISTORY_STRIP_FIELDS as field \(field\)\}/);
	assert.equal(HISTORY_STRIP_FIELDS.length, 4);
	const keys = [
		'historyStripFieldGeneration',
		'historyStripFieldModel',
		'historyStripFieldEngineVersion',
		'historyStripFieldBytes'
	];
	assert.equal(keys.length, HISTORY_STRIP_FIELDS.length);
	for (const key of keys) {
		assert.ok(PANEL.includes(`t().${key}`), `${key} is not read by the panel`);
		assert.match(JA, new RegExp(`\\n\\t${key}: '`), `${key} has no Japanese`);
		assert.match(EN, new RegExp(`\\n\\t${key}: '`), `${key} has no English`);
	}
});

test('T-152  a box that cannot be ticked is disabled, so the limit is visible', () => {
	// Without this the third click is simply inert, which reads as a bug.
	assert.match(PANEL, /disabled=\{historyStripFieldsSaving \|\| \(!checked && !canAddHistoryStripField\(historyStripFields\)\)\}/);
});

test('T-163  the file size is read from the server, not counted from what arrived', () => {
	// The listing that fills the strip asks for include_svg=false, so `svg` is an
	// empty string by the time it gets here. Counting it reported every work but
	// the open one as 0 B -- seen on screen, five works, four of them wrong.
	assert.match(STRIP, /const bytes = item\.svg_bytes \?\? 0;/);
	assert.ok(!STRIP.includes('measureSvgWeight'), 'the strip must not measure what it was sent');
	// And the listing really does withhold the picture, which is why.
	const HISTORY_OWNER = readFileSync(new URL('./features/history/browsing-state.svelte.ts', import.meta.url), 'utf-8');
	assert.match(HISTORY_OWNER, /include_svg: 'false'/);
});
