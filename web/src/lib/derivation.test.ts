// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { derivationDetail } from './derivation.ts';

test('a form change names both forms; other kinds and a half-recorded change add nothing', () => {
	const metadata = { form_from: 'dividing_line', form_to: 'bands' };
	assert.equal(derivationDetail('composition_form_change', metadata, true), '画の型: 分ける線 → 帯');
	assert.match(derivationDetail('composition_form_change', metadata, false) ?? '', /^Form: .+ → .+$/);
	assert.equal(derivationDetail('composition_form_change', { form_from: null, form_to: 'bands' }, true), null);
	assert.equal(derivationDetail('composition_form_change', undefined, true), null);
	assert.equal(derivationDetail('layout_change', metadata, true), null);
});
