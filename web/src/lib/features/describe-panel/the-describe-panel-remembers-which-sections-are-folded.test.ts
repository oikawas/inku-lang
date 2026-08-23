// Run with: npm run test:unit  (node:test, no test dependency)
//
// Acceptance for the two folds of the describe panel -- 写生 (Stage 0.5) and
// 展開後 (Stage 2 input).  T-16 (the round trip and the two defaults), T-17
// (the viewer stopped owning its own fold), T-18 (the sketch body is inside
// the fold and its head is not), T-19 (the folds reach the server).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import {
	DDL_EXPANDED_DEFAULT,
	DDL_EXPANDED_FIELD,
	DEFAULT_FOLDS,
	foldsFromSettings,
	foldsToSettings,
	SKETCH_DEFAULT,
	SKETCH_FIELD,
	storedFold
} from './folds.ts';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');

// ------------------------------------------------- T-16 (round trip, defaults)

test('T-16: the two sections do not share a default', () => {
	// The sketch prose was on screen before it could be folded; the expanded
	// DDL was not. One shared default would silently change one of them.
	assert.equal(SKETCH_DEFAULT, true);
	assert.equal(DDL_EXPANDED_DEFAULT, false);
	assert.notEqual(SKETCH_DEFAULT, DDL_EXPANDED_DEFAULT);
	assert.deepEqual(DEFAULT_FOLDS, { sketchOpen: true, ddlExpandedOpen: false });
});

test('T-16: a user who has never folded anything gets each default, not one of them', () => {
	assert.deepEqual(foldsFromSettings(null), DEFAULT_FOLDS);
	assert.deepEqual(foldsFromSettings(undefined), DEFAULT_FOLDS);
	assert.deepEqual(foldsFromSettings({}), DEFAULT_FOLDS);
	// Another feature's settings are not ours.
	assert.deepEqual(foldsFromSettings({ color_catalog_id: 'default' }), DEFAULT_FOLDS);
});

test('T-16: a fold survives the round trip in both directions', () => {
	const folded = { sketchOpen: false, ddlExpandedOpen: true };
	assert.deepEqual(foldsFromSettings(foldsToSettings(folded)), folded);
	const opened = { sketchOpen: true, ddlExpandedOpen: false };
	assert.deepEqual(foldsFromSettings(foldsToSettings(opened)), opened);
});

test('T-16: each field carries only its own section', () => {
	// A save that names one section must not move the other one.
	assert.deepEqual(foldsFromSettings({ [SKETCH_FIELD]: false }), {
		sketchOpen: false,
		ddlExpandedOpen: DDL_EXPANDED_DEFAULT
	});
	assert.deepEqual(foldsFromSettings({ [DDL_EXPANDED_FIELD]: true }), {
		sketchOpen: SKETCH_DEFAULT,
		ddlExpandedOpen: true
	});
});

test('T-16: a stored value that is not a boolean falls back to that section, not to false', () => {
	// The server stores booleans, but an older row or a hand-edited one may
	// hold anything. Falling back to a shared false would fold the sketch.
	assert.equal(storedFold({ [SKETCH_FIELD]: 'yes' }, SKETCH_FIELD, SKETCH_DEFAULT), true);
	assert.equal(storedFold({ [SKETCH_FIELD]: 1 }, SKETCH_FIELD, SKETCH_DEFAULT), true);
	assert.equal(storedFold({ [SKETCH_FIELD]: null }, SKETCH_FIELD, SKETCH_DEFAULT), true);
	assert.equal(
		storedFold({ [DDL_EXPANDED_FIELD]: 'yes' }, DDL_EXPANDED_FIELD, DDL_EXPANDED_DEFAULT),
		false
	);
	// A real stored false is a fold, not an absence.
	assert.equal(storedFold({ [SKETCH_FIELD]: false }, SKETCH_FIELD, SKETCH_DEFAULT), false);
});

// -------------------------------------------------- T-17 (the viewer's fold)

test("T-17: the expanded DDL fold is the user's, not the viewer instance's", () => {
	const viewer = read('../../components/DdlViewer.svelte');
	// The instance-local fold is what made it forget on every reload.
	assert.doesNotMatch(viewer, /let expandedOpen = \$state/);
	assert.match(viewer, /describePanelSettings\.ddlExpandedOpen/);
	assert.match(viewer, /onclick=\{describePanelSettings\.toggleDdlExpanded\}/);
});

// ------------------------------------------- T-18 (what the sketch fold hides)

test('T-18: the sketch body is inside the fold and the head is not', () => {
	const page = read('../../../routes/+page.svelte');
	const start = page.indexOf('<section class="panel-section sketch-section">');
	const end = page.indexOf('</section>', start);
	assert.ok(start > 0 && end > start, 'the sketch section is missing');
	const section = page.slice(start, end);

	// The head stays visible when folded: it carries the toggle itself, the
	// grain the work was drawn at, and the way into editing.
	const headEnd = section.indexOf('</div>');
	const head = section.slice(0, headEnd);
	assert.match(head, /onclick=\{describePanelSettings\.toggleSketch\}/);
	assert.match(head, /sketch-grain/);
	assert.match(head, /sketch-edit-btn/);

	// Everything that shows the prose is behind the fold.
	const body = section.slice(headEnd);
	assert.match(body, /\{#if describePanelSettings\.sketchOpen\}/);
	const guarded = body.slice(body.indexOf('{#if describePanelSettings.sketchOpen}'));
	for (const marker of ['sketch-body', 'sketch-editor', 'sketch-note']) {
		assert.match(guarded, new RegExp(marker), `${marker} is outside the fold`);
	}
	assert.doesNotMatch(body.slice(0, body.indexOf('{#if describePanelSettings.sketchOpen}')), /sketch-body/);
});

test('T-18: opening the editor unfolds the prose it edits', () => {
	const page = read('../../../routes/+page.svelte');
	assert.match(page, /work\.sketchEditing = !work\.sketchEditing; if \(work\.sketchEditing\) describePanelSettings\.revealSketch\(\)/);
});

// ------------------------------------------------ T-19 (the folds are saved)

test("T-19: both folds are registered as the user's settings, not the browser's", () => {
	const settings = read('./settings.svelte.ts');
	assert.match(settings, /registerUserSettingsContributor\(\{/);
	assert.match(settings, /id: 'describe-panel'/);
	// localStorage would be per browser, which is the wrong grain here. Match
	// the mechanism, not the word: the file says "rather than in localStorage"
	// in its own comment, and a gate that reads prose measures the prose.
	assert.doesNotMatch(settings, /localStorage\s*\.\s*\w+Item/);
	assert.doesNotMatch(settings, /registerPersistedSetting/);
	assert.doesNotMatch(settings, /from '\$lib\/features\/persisted-settings'/);
	// The restore is unconditional, so the next user does not inherit a fold.
	assert.match(settings, /apply: \(settings\) => \{[\s\S]*?foldsFromSettings\(settings\)/);
});

test('T-19: every toggle writes its own field to the server', () => {
	const settings = read('./settings.svelte.ts');
	assert.match(settings, /toggleSketch = \(\) => \{[\s\S]*?persist\(\{ \[SKETCH_FIELD\]/);
	assert.match(settings, /toggleDdlExpanded = \(\) => \{[\s\S]*?persist\(\{ \[DDL_EXPANDED_FIELD\]/);

	const page = read('../../../routes/+page.svelte');
	const writer = page.slice(
		page.indexOf('async function persistDescribePanelFolds'),
		page.indexOf('bindDescribePanelPersist(')
	);
	assert.ok(writer.length > 0, 'the page never writes the folds');
	assert.match(writer, /\/api\/auth\/me\/settings/);
	assert.match(writer, /method: 'PATCH'/);
	assert.match(writer, /model_settings: fields/);
	assert.match(page, /bindDescribePanelPersist\(/);
});

test('T-19: the server keeps both fields, so the save is not silently dropped', () => {
	// Unknown keys do not survive normalize_user_model_settings: a web-only
	// change here would round-trip to the default on the next login.
	const model = readFileSync(
		new URL('../../../../../server/src/inku_server/model_settings.py', import.meta.url),
		'utf8'
	);
	assert.match(model, /"sketch_open": True/);
	assert.match(model, /"ddl_expanded_open": False/);
	assert.match(model, /clean\["sketch_open"\] = settings\.get\("sketch_open"\) is not False/);
	assert.match(model, /clean\["ddl_expanded_open"\] = settings\.get\("ddl_expanded_open"\) is True/);
});
