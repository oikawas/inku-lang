import assert from 'node:assert/strict';
import { test } from 'node:test';
import { COMPOSITION_FORMS, compositionFormOptions } from './composition-form.ts';
import { ja } from '../../i18n/ja.ts';
import { en } from '../../i18n/en.ts';

test('both languages describe the same seven core forms', () => {
	for (const strings of [ja, en]) {
		const options = compositionFormOptions(strings);
		assert.deepEqual(options.map((option) => option.id), [...COMPOSITION_FORMS]);
		assert.ok(options.every((option) => option.name && option.description));
	}
});
