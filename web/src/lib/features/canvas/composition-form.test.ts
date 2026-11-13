import assert from 'node:assert/strict';
import { test } from 'node:test';
import { COMPOSITION_FORMS, compositionFormOptions } from './composition-form.ts';
import { ja } from '../../i18n/ja.ts';
import { en } from '../../i18n/en.ts';

test('both languages describe the same seven core forms', () => {
	for (const isJapanese of [true, false]) {
		const options = compositionFormOptions(isJapanese);
		assert.deepEqual(options.map((option) => option.id), [...COMPOSITION_FORMS]);
		assert.ok(options.every((option) => option.name && option.description));
	}
});

// The page's own arrays stay for macOS, which reads them through
// ui-reference.json; they must say what the names table says.
test('the language packs keep the names table\'s form names and descriptions', () => {
	for (const [strings, isJapanese] of [[ja, true], [en, false]] as const) {
		const options = compositionFormOptions(isJapanese);
		assert.deepEqual([...strings.compositionFormNames], options.map((option) => option.name));
		assert.deepEqual([...strings.compositionFormDescriptions], options.map((option) => option.description));
	}
});
