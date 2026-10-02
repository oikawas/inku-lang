// Acceptance for the retained sketch fold and the retired expanded DDL fold.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import {
	DEFAULT_FOLDS,
	foldsFromSettings,
	foldsToSettings,
	SKETCH_DEFAULT,
	SKETCH_FIELD,
	storedFold
} from './folds.ts';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');

// ------------------------------------------------- T-16 (round trip, defaults)

test('T-16: the retained sketch section defaults open', () => {
	assert.equal(SKETCH_DEFAULT, true);
	assert.deepEqual(DEFAULT_FOLDS, { sketchOpen: true });
});

test('T-16: a user who has never folded anything gets each default, not one of them', () => {
	assert.deepEqual(foldsFromSettings(null), DEFAULT_FOLDS);
	assert.deepEqual(foldsFromSettings(undefined), DEFAULT_FOLDS);
	assert.deepEqual(foldsFromSettings({}), DEFAULT_FOLDS);
	// Another feature's settings are not ours.
	assert.deepEqual(foldsFromSettings({ color_catalog_id: 'default' }), DEFAULT_FOLDS);
});

test('T-16: a fold survives the round trip in both directions', () => {
	const folded = { sketchOpen: false };
	assert.deepEqual(foldsFromSettings(foldsToSettings(folded)), folded);
	const opened = { sketchOpen: true };
	assert.deepEqual(foldsFromSettings(foldsToSettings(opened)), opened);
});

test('T-16: a retired expanded key cannot move the sketch section or return on save', () => {
	assert.deepEqual(foldsFromSettings({ sketch_open: false, ddl_expanded_open: true }), { sketchOpen: false });
	assert.deepEqual(foldsFromSettings({ ddl_expanded_open: false }), DEFAULT_FOLDS);
	assert.deepEqual(foldsToSettings(foldsFromSettings({ ddl_expanded_open: true })), { sketch_open: true });
});

test('T-16: a stored value that is not a boolean falls back to that section, not to false', () => {
	// The server stores booleans, but an older row or a hand-edited one may
	// hold anything. Falling back to a shared false would fold the sketch.
	assert.equal(storedFold({ [SKETCH_FIELD]: 'yes' }, SKETCH_FIELD, SKETCH_DEFAULT), true);
	assert.equal(storedFold({ [SKETCH_FIELD]: 1 }, SKETCH_FIELD, SKETCH_DEFAULT), true);
	assert.equal(storedFold({ [SKETCH_FIELD]: null }, SKETCH_FIELD, SKETCH_DEFAULT), true);
	// A real stored false is a fold, not an absence.
	assert.equal(storedFold({ [SKETCH_FIELD]: false }, SKETCH_FIELD, SKETCH_DEFAULT), false);
});

// -------------------------------------------------- T-17 (the viewer's fold)

test('T-17: the viewer has one visible source and no expanded fold', () => {
	const viewer = read('../../components/DdlViewer.svelte');
	// The instance-local fold is what made it forget on every reload.
	assert.match(viewer, /highlightDDL\(ddl\)/);
	assert.doesNotMatch(viewer, /expandedDdl|expandedOpen|toggleDdlExpanded/);
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

test("T-19: the sketch fold is registered as the user's settings, not the browser's", () => {
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
	assert.doesNotMatch(settings, /DDL_EXPANDED_FIELD|toggleDdlExpanded/);

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

test('T-19: the server keeps the sketch fold and ignores the retired field', () => {
	// Unknown keys do not survive normalize_user_model_settings: a web-only
	// change here would round-trip to the default on the next login.
	const model = readFileSync(
		new URL('../../../../../server/src/inku_server/model_settings.py', import.meta.url),
		'utf8'
	);
	assert.match(model, /"sketch_open": True/);
	assert.match(model, /clean\["sketch_open"\] = settings\.get\("sketch_open"\) is not False/);
	assert.doesNotMatch(model, /ddl_expanded_open/);
});
