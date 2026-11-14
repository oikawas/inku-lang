// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { derivationDetail, derivationKindLabel } from './derivation.ts';

test('step 3: a moved thing names the thing and both places', () => {
	const metadata = { place: { title: '磯の岩肌', thing: 2, at_from: 'golden_lr', at: 'center' } };
	assert.equal(derivationDetail('layout_change', metadata, true), '磯の岩肌: 黄金分割・右下の交点 → 中心');
	assert.equal(derivationDetail('layout_change', { place: { ...metadata.place, at_from: null } }, false),
		'磯の岩肌: off the places → Center');
	// A layout change of the near/chance choice records no place.
	assert.equal(derivationDetail('layout_change', { recomposition: { mode: 'near' } }, true), null);
});

test('step 2: a main-law change names both laws, and the kind reads "composition and laws"', () => {
	const metadata = { main_law_from: 'B1', main_law_to: 'B10', form: 'one_corner' };
	assert.equal(derivationDetail('composition_form_change', metadata, true), '主の法則: 黄金分割 → 漸進');
	assert.equal(derivationDetail('composition_form_change', metadata, false), 'Main law: Golden section → Progression');
	assert.equal(derivationDetail('composition_form_change', { main_law_from: null, main_law_to: 'B10', form: null }, true), null);
	assert.equal(derivationKindLabel('composition_form_change', true), '構図と法則');
	assert.equal(derivationKindLabel('composition_form_change', false), 'Composition and laws');
	// A moved thing's child is named by what it changed: the place, not the composition (step 3).
	assert.equal(derivationKindLabel('layout_change', true), '配置');
});

test('a form change names both forms; other kinds and a half-recorded change add nothing', () => {
	const metadata = { form_from: 'dividing_line', form_to: 'bands' };
	assert.equal(derivationDetail('composition_form_change', metadata, true), '画の型: 分ける線 → 帯');
	assert.match(derivationDetail('composition_form_change', metadata, false) ?? '', /^Form: .+ → .+$/);
	assert.equal(derivationDetail('composition_form_change', { form_from: null, form_to: 'bands' }, true), null);
	assert.equal(derivationDetail('composition_form_change', undefined, true), null);
	assert.equal(derivationDetail('layout_change', metadata, true), null);
});

test('step 4c: a thesis change names the heads of both theses', () => {
	const metadata = { thesis_from: '広い海面から斜めに迫る波を画面の右下に置く。', thesis_to: '磯の岩を画面の左上に大きく据え、波の筋を走らせる。', thesis_source: 'proposed' };
	assert.equal(derivationDetail('composition_form_change', metadata, true), '命題: 広い海面から斜めに迫る波を画… → 磯の岩を画面の左上に大きく据…');
	assert.equal(derivationDetail('composition_form_change', { ...metadata, thesis_from: null }, false), 'Thesis: — → 磯の岩を画面の左上に大きく据…');
});
