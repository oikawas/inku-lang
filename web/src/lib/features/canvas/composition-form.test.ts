import assert from 'node:assert/strict';
import { test } from 'node:test';
import { COMPOSITION_FORMS, MAIN_LAWS, compositionFormOptions, mainLawFamilies } from './composition-form.ts';
import { COMPOSITION_NAMES } from '../../composition-names.generated.ts';

test('the main laws are every law of the names table but B21, grouped in five families', () => {
	assert.deepEqual([...MAIN_LAWS], COMPOSITION_NAMES.laws.map((law) => law.code).filter((code) => code !== 'B21'));
	assert.deepEqual(mainLawFamilies(true).map((family) => family.family), ['比例', '均衡', '律動', '階調', 'カード']);
	assert.deepEqual(mainLawFamilies(false).map((family) => family.laws.length), [5, 3, 3, 1, 6]);
	assert.ok(mainLawFamilies(true).flatMap((family) => family.laws).every((law) => law.name && law.summary));
});
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
