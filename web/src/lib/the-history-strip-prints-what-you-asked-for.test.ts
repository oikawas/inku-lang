// Run with: npm run test:unit  (node:test, no test dependency)
//
// The history strip used to print the generation and the Stage 1 model, fixed.
// Four facts are on offer now, at most three at a time, and none is an answer.
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
	abbreviateStripModel,
	canAddHistoryStripField,
	DEFAULT_HISTORY_STRIP_FIELDS,
	formatHistoryStripEngineVersion,
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

test('T-148  at most three survive, in the order the four are declared', () => {
	assert.equal(HISTORY_STRIP_FIELD_LIMIT, 3);
	assert.deepEqual(normalizeHistoryStripFields(['bytes', 'generation']), ['generation', 'bytes']);
	assert.deepEqual(normalizeHistoryStripFields(['bytes', 'bytes']), ['bytes']);
	assert.deepEqual(normalizeHistoryStripFields(['nope', 'bytes']), ['bytes']);
	assert.deepEqual(normalizeHistoryStripFields(['bytes', 'generation', 'model']), ['generation', 'model', 'bytes']);
	const four = normalizeHistoryStripFields(['generation', 'model', 'engine_version', 'bytes']);
	assert.equal(four.length, HISTORY_STRIP_FIELD_LIMIT);
});

test('T-149  a fourth tick is refused rather than evicting one of the three', () => {
	const two: HistoryStripField[] = ['generation', 'model'];
	assert.equal(canAddHistoryStripField(two), true);
	const three = toggleHistoryStripField(two, 'bytes');
	assert.deepEqual(three, ['generation', 'model', 'bytes']);
	assert.equal(canAddHistoryStripField(three), false);
	// The refusal keeps all three -- an eviction would silently move a choice
	// the reader made, and they would find out by reading the strip.
	assert.deepEqual(toggleHistoryStripField(three, 'engine_version'), three);
	// Unticking always works, and then the fourth fits.
	const back = toggleHistoryStripField(three, 'model');
	assert.deepEqual(back, ['generation', 'bytes']);
	assert.equal(canAddHistoryStripField(back), true);
	assert.deepEqual(toggleHistoryStripField(back, 'engine_version'), ['generation', 'engine_version', 'bytes']);
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
	assert.doesNotMatch(PANEL, /historyStripFieldsFull/);
	assert.doesNotMatch(JA, /historyStripFieldsFull/);
	assert.doesNotMatch(EN, /historyStripFieldsFull/);
});

test('the engine version printed under a thumbnail uses the Ver. prefix', () => {
	assert.equal(formatHistoryStripEngineVersion('41', 'not recorded'), 'Ver.41');
	assert.equal(formatHistoryStripEngineVersion('Ver.41', 'not recorded'), 'Ver.41');
	assert.equal(formatHistoryStripEngineVersion(null, 'not recorded'), 'not recorded');
	assert.match(STRIP, /formatHistoryStripEngineVersion\(item\.render_engine_version, t\(\)\.historyVersionNotRecorded\)/);
});

test('the history work tooltip labels the render version compactly', () => {
	assert.match(STRIP, /<span>Render<\/span><strong>\{it\.render_engine_version/);
	assert.doesNotMatch(STRIP, />Render engine version</);
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

test('the model is printed as provider (2), family (3) and version (3)', () => {
	// The table the author chose on 2026-09-29.
	const cases: [string, string, string][] = [
		['Claude API (Cloud)', 'Claude Sonnet 5', 'Cl Son 5'],
		['Claude API (Cloud)', 'Claude Opus 4.7', 'Cl Opu 4.7'],
		['Claude API (Cloud)', 'Claude Haiku 4.5', 'Cl Hai 4.5'],
		['Gemini API (Cloud)', 'Gemini 3.5 Flash-Lite', 'Ge Gem 3.5'],
		['Gemini API (Cloud)', 'Gemma 4 31B Instruct', 'Ge Gem 4'],
		['OpenAI API Platform', 'GPT-5.1 mini', 'Op GPT 5.1'],
		['NVIDIA NIM (Cloud)', 'gemma-4-31b-it', 'NV gem 4'],
		['Ollama Cloud (ollama.com)', 'gemma4:31b', 'Ol gem 4']
	];
	for (const [owner, name, expected] of cases) assert.equal(abbreviateStripModel(owner, name), expected, name);
});
