// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { derivationDetail, derivationKindLabel } from './derivation.ts';

test('step 2: a main-law change names both laws, and the kind reads "composition and laws"', () => {
	const metadata = { main_law_from: 'B1', main_law_to: 'B10', form: 'one_corner' };
	assert.equal(derivationDetail('composition_form_change', metadata, true), '主の法則: 黄金分割 → 漸進');
	assert.equal(derivationDetail('composition_form_change', metadata, false), 'Main law: Golden section → Progression');
	assert.equal(derivationDetail('composition_form_change', { main_law_from: null, main_law_to: 'B10', form: null }, true), null);
	assert.equal(derivationKindLabel('composition_form_change', true), '構図と法則');
	assert.equal(derivationKindLabel('composition_form_change', false), 'Composition and laws');
});

test('a form change names both forms; other kinds and a half-recorded change add nothing', () => {
	const metadata = { form_from: 'dividing_line', form_to: 'bands' };
	assert.equal(derivationDetail('composition_form_change', metadata, true), '画の型: 分ける線 → 帯');
	assert.match(derivationDetail('composition_form_change', metadata, false) ?? '', /^Form: .+ → .+$/);
	assert.equal(derivationDetail('composition_form_change', { form_from: null, form_to: 'bands' }, true), null);
	assert.equal(derivationDetail('composition_form_change', undefined, true), null);
	assert.equal(derivationDetail('layout_change', metadata, true), null);
});
