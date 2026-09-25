import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

/**
 * T-64 and T-65: the button that finishes a batch which stopped part-way.
 *
 * The rules it runs on are driven for real in features/batch/resume.test.ts.
 * What is read here is the wiring that carries the answer to the screen, which
 * has no harness to run in: `test:unit` is `node --test` with no DOM.
 */

const PANEL = readFileSync(fileURLToPath(new URL('./BatchPanel.svelte', import.meta.url)), 'utf8');
const PAGE = readFileSync(fileURLToPath(new URL('../../routes/+page.svelte', import.meta.url)), 'utf8');
const OWNER = readFileSync(fileURLToPath(new URL('../features/batch/state.svelte.ts', import.meta.url)), 'utf8');

test('T-64  the resume button is withheld unless there is something to finish', () => {
	// 2026-09-22: the button became a resume card, also withheld while a run is
	// going (the run's own progress and stop take its place).
	assert.match(PANEL, /\{#if !batchRunning && canResumeBatch\}/, 'the resume button no longer depends on the flag');
	// Null the rest of the time -- an empty history and a run that reached its
	// last line are the same answer here, and both withhold the button.
	assert.match(PAGE, /canResumeBatch=\{batch\.canResume\}/, 'the flag is not the canonical resume state');
	assert.match(OWNER, /if \(!this\.deps\.signedIn\(\) \|\| !prompt\)/,
		'a member with no stored batch is offered a resume');
});

test('T-64  it comes before the button that starts a new run', () => {
	// 2026-09-22: the resume card moved out of the paint button's row to sit
	// above the next run's conditions, so the order is read across the panel:
	// the card, then the conditions, then the new-run button.
	const card = PANEL.indexOf('<section class="batch-resume-card"');
	const conditions = PANEL.indexOf('<section class="batch-next-conditions"');
	const row = PANEL.match(/<div class="batch-actions"[^>]*>[\s\S]*?<\/div>/);
	assert.ok(row, 'the new-run button is no longer in its row');
	assert.match(row[0], /<PaintButton[^>]*>\{t\(\)\.batchNewRunBtn\}<\/PaintButton>/);
	assert.ok(card > 0 && card < conditions, 'the resume card is not before the conditions');
	assert.ok(conditions < PANEL.indexOf(row[0]), 'the conditions are not before the new-run button');
	assert.ok(PANEL.slice(card, conditions).includes('batch-resume-btn'), 'the resume button left its card');
});

test('T-65  a resumed run paints the plan, not the box', () => {
	assert.match(OWNER, /const paintLines = options\.resumeLines \?\? lines;/, 'the resume plan is not what gets painted');
	// Every quantity the run reads has to come from the plan, or the progress
	// readout counts one thing while the loop paints another.
	assert.match(OWNER, /const lineTotal = paintLines\.length;/);
	assert.match(OWNER, /for \(let index = 0; index < paintLines\.length; index \+= 1\)/);
	assert.match(OWNER, /await paintBatchLine\(paintLines\[index\]\)/);
});

test('T-65  the numbers on the works come from the prompt, not from the plan', () => {
	// `item.line` throughout, never the loop index: resuming at line 7 has to put
	// #7 on the work, and a plan of what is left would otherwise restart at #1.
	assert.match(OWNER, /historyInput: `#\$\{item\.line\} \$\{item\.input\}`/);
	assert.match(OWNER, /displayLabel: `#\$\{item\.line\}`/);
	assert.match(OWNER, /batchLineNumber: item\.line/);
	// And the box is refilled with the whole batch, which is what those numbers
	// number. The snapshot carries the candidate's prompt, or the session's.
	assert.match(OWNER, /prompt: candidate\.prompt,/);
	assert.match(OWNER, /this\.input = snapshot\.prompt;/);
});

test('T-65  the answer is asked for again when a run ends', () => {
	// A run that was stopped leaves lines to finish and a run that reached the
	// end leaves none; without this the button outlives the run it belonged to.
	assert.match(OWNER, /await this\.refreshResume\(\);/, 'the resume state is not refreshed after a run');
	assert.match(PAGE, /if \(mode === 'batch'\) void untrack\(\(\) => batch\.refreshResume\(\)\)/, 'the batch tab does not ask on arrival');
});

test('T-66  resuming an auto run resumes under auto, not under what it resolved to', () => {
	// [I-257]. The order matters: testing the resolved id first would pin the
	// catalog before the mode was ever looked at.
	assert.match(PAGE, /if \(conditions\.catalogMode === 'auto'\) colorCatalogSettings\.selected = AUTO_CATALOG_ID;/);
	assert.match(PAGE, /else if \(conditions\.catalogId\) colorCatalogSettings\.selected = conditions\.catalogId;/);
	assert.ok(
		PAGE.indexOf("conditions.catalogMode === 'auto'") < PAGE.indexOf('else if (conditions.catalogId)'),
		'the resolved id is tested after the catalog it resolved to, so auto can never win',
	);
});

test('T-66  the mode reaches the row it is read from', () => {
	// A field the client never sends is a column that is always null, and the
	// gate above would then be green while nothing was ever restored.
	const SCHEMA = readFileSync(
		fileURLToPath(new URL('../../../../server/src/inku_server/persistence/schema.py', import.meta.url)),
		'utf8',
	);
	const LEGACY_SCHEMA = readFileSync(
		fileURLToPath(new URL('../../../../server/src/inku_server/persistence/legacy_schema.py', import.meta.url)),
		'utf8',
	);
	const HISTORY = readFileSync(
		fileURLToPath(new URL('../../../../server/src/inku_server/persistence/history.py', import.meta.url)),
		'utf8',
	);
	const server = (name: string) => readFileSync(
		fileURLToPath(new URL(`../../../../server/src/inku_server/${name}`, import.meta.url)),
		'utf8',
	);
	assert.match(SCHEMA, /^ {4}catalog_mode = Column\(String, +nullable=True\)$/m, 'the row has no column for it');
	assert.match(LEGACY_SCHEMA, /"catalog_mode": "ALTER TABLE history ADD COLUMN catalog_mode VARCHAR"/, 'an existing database never gets the column');
	assert.match(HISTORY, /"catalog_mode": row\.catalog_mode,/, 'the column is stored but never handed back');
	// Since the shared-pipeline cutover (2026-09-14) the paint route hands the
	// whole request to the compatibility layer, and the product host writes the
	// row: each link has to keep the mode.
	assert.match(server('api_core/routers/render.py'), /_pipeline_compat\.paint\(\s*actor\["id"\], req\.model_dump\(mode="json"\)/, 'the paint route drops the request');
	assert.match(server('pipeline_compat.py'), /"catalog_mode": "catalog_mode",/, 'the paint route drops the mode on the way to the row');
	assert.match(server('pipeline_product.py'), /"catalog_mode": settings\["catalog_mode"\],/, 'the host saves the work without the mode');
});
