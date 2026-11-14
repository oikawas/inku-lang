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

// Step 4c: a thesis the author writes or one the AI proposed.
import { MAX_THESIS_CHARS, compositionChangeOptions, thesisHead, thesisWritable } from './composition-form.ts';

test('a thesis change sends the thesis, who wrote it and, for a proposed one, its digest', () => {
	const parent = { form: 'one_corner', mainLaw: 'B1', thesis: '今の命題。' };
	assert.deepEqual(compositionChangeOptions({ kind: 'thesis', thesis: '  磯の岩を左上に据える。 ', source: 'author' }, parent), {
		options: { composition_thesis: '磯の岩を左上に据える。', composition_thesis_source: 'author' },
		metadata: { thesis_from: '今の命題。', thesis_to: '磯の岩を左上に据える。', thesis_source: 'author' },
	});
	assert.deepEqual(compositionChangeOptions({ kind: 'thesis', thesis: '波の筋を走らせる。', source: 'proposed', digest: 'sha256:abc' }, { form: null, mainLaw: null }), {
		options: { composition_thesis: '波の筋を走らせる。', composition_thesis_source: 'proposed', composition_thesis_prompt_digest: 'sha256:abc' },
		metadata: { thesis_from: null, thesis_to: '波の筋を走らせる。', thesis_source: 'proposed' },
	});
});

test('a thesis may be fixed from one to 400 characters, and its head is cut with an ellipsis', () => {
	assert.equal(thesisWritable('   '), false);
	assert.equal(thesisWritable('あ'), true);
	assert.equal(thesisWritable('あ'.repeat(MAX_THESIS_CHARS)), true);
	assert.equal(thesisWritable('あ'.repeat(MAX_THESIS_CHARS + 1)), false);
	assert.equal(thesisHead('短い命題。'), '短い命題。');
	assert.equal(thesisHead('広い海面から斜めに迫る波を画面の右下に置く。'), '広い海面から斜めに迫る波を画…');
});
