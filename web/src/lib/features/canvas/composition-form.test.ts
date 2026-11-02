import assert from 'node:assert/strict';
import { test } from 'node:test';
import { COMPOSITION_FORMS, compositionFormOptions } from './composition-form.ts';

test('both languages describe the same seven core forms', () => {
	for (const japanese of [true, false]) {
		const options = compositionFormOptions(japanese);
		assert.deepEqual(options.map((option) => option.id), [...COMPOSITION_FORMS]);
		assert.ok(options.every((option) => option.name && option.description));
	}
});
