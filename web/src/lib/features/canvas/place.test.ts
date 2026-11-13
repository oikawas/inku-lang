// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';

import { PLACES, offersPlaces, placeLabel, placeOfBox, placeRows, type PlaceTarget } from './place.ts';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');

const all = (outcome: string) => Object.fromEntries(PLACES.map((place) => [place.id, outcome]));
const TARGET: PlaceTarget = {
	workId: 'w',
	units: [
		{ title: '大海の', thing: 1, lines: [3, 4], box: [0.08, 0.2, 0.9, 0.45], places: { ...all('ok'), golden_ul: 'clamped' } },
		{ title: '磯もとどろに', thing: 2, lines: [5], box: [0.4, 0.4, 0.84, 0.82], places: { ...all('ok'), golden_lr: 'unchanged' } },
		{ title: '若葉', thing: null, lines: [6], box: null, places: all('scene_word') },
	],
	things: [{ thing: 1, role: 'field', what: '広い海面' }, { thing: 2, role: 'secondary', what: '磯の岩肌' }],
	freeLines: false,
};

test('the core\'s nine places sit where its AT puts them', () => {
	assert.deepEqual(PLACES.map((place) => place.id), [
		'golden_ul', 'golden_ur', 'golden_ll', 'golden_lr', 'third_left', 'third_right', 'third_top', 'third_bottom', 'center']);
	const core = read('../../../../../core/crates/inku-pipeline/src/chunk_moves.rs');
	for (const place of PLACES) assert.match(core, new RegExp(`"${place.id}"`), place.id);
});

test('a box\'s place: a point before a line, within 0.02 as the core reads it', () => {
	assert.equal(placeOfBox([0.4, 0.4, 0.84, 0.82]), 'golden_lr');
	// The center (0.5, 0.33) is on the upper third line; (0.5, 0.15) is at no place.
	assert.equal(placeOfBox([0.45, 0.1, 0.55, 0.56]), 'third_top');
	assert.equal(placeOfBox([0.45, 0.05, 0.55, 0.25]), null);
	assert.equal(placeOfBox([0.3, 0.6, 0.36, 0.9]), 'third_left');
	assert.equal(placeOfBox(null), null);
});

test('each chunk is a row with its thing, and one that no place takes is held', () => {
	const rows = placeRows(TARGET, true);
	assert.deepEqual(rows.map((row) => [row.number, row.role, row.what, row.now, row.movable]), [
		[1, '場', '広い海面', 'third_top', true],
		[2, '従', '磯の岩肌', 'golden_lr', true],
		[3, '', '若葉', null, false],
	]);
	assert.equal(placeLabel(rows[0], 'golden_ul', true, '（画面の端で止まる）'), '広い海面 → 黄金分割・左上の交点（画面の端で止まる）');
	assert.equal(placeLabel(rows[1], 'center', false, ' (edge)'), '磯の岩肌 → Center');
	assert.equal(offersPlaces(TARGET), true);
	assert.equal(offersPlaces({ ...TARGET, units: [TARGET.units[2]] }), false);
	assert.equal(offersPlaces({ ...TARGET, units: [] }), false);
});

test('step 3: "Change the layout" shows the places when a chunk can move, else the near/chance choice', () => {
	const shell = read('./CanvasRefinementWorkspace.svelte');
	const view = read('./RefinementPlaceView.svelte');
	assert.match(shell, /view === 'layout' && placeTarget && offersPlaces\(placeTarget\)/);
	assert.match(shell, /<RefinementPlaceView/);
	assert.match(shell, /<RefinementAdjustView/);
	// A place it cannot take still says why when pointed at: not disabled, aria-disabled.
	assert.match(view, /aria-disabled=\{!pressable\(place\.id\)\}/);
	assert.doesNotMatch(view, /\sdisabled=\{!pressable/);
	assert.match(view, /class="keeps"/);
	// A work with free lines says they may be drawn again (the author's choice after the measure).
	assert.match(view, /target\.freeLines \? t\(\)\.placeKeepsFreeLines : t\(\)\.placeKeeps/);
	const coordinator = read('./refinement-coordinator.svelte.ts');
	// The option is a DDL fork saved as a layout change, never a send.
	assert.match(coordinator, /pipeline\.fromDdl\(ddl,/);
	assert.match(coordinator, /derivation_kind: 'layout_change', derivation_metadata: metadata/);
	assert.match(coordinator, /\/chunk-place`/);
});
