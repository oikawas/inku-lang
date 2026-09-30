// Run with: npm run test:unit  (node:test, no test dependency)
//
// The meter under the description names the verse form the description is,
// and only when it is close to one. Japanese is judged in sounds -- by its
// phrases when it is set out in them, otherwise by its total, within two
// sounds. English is judged in lines, and by syllables where the form is made
// of them. Either language can be switched off, leaving the count alone.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { describeLength, englishForm, englishSyllables, formByTotal, japaneseForm } from './verseForm.ts';

const ON = { japanese: true, english: true };

test('a total names a form only within two sounds of it', () => {
	assert.equal(formByTotal(17)?.form, 'haiku-senryu');
	assert.equal(formByTotal(19)?.form, 'katauta');
	assert.equal(formByTotal(26)?.form, 'dodoitsu');
	assert.equal(formByTotal(33)?.form, 'tanka');
	assert.equal(formByTotal(38)?.form, 'sedoka-bussokuseki');
	assert.deepEqual(formByTotal(55), { form: 'choka', length: 55 });
	// 18 is within two of both 17 and 19: the nearer, and a tie goes to the shorter.
	assert.equal(formByTotal(18)?.form, 'haiku-senryu');
	// The author's prose, 52 sounds, is no form.
	assert.equal(formByTotal(52), null);
	assert.equal(formByTotal(23), null);
});

test('phrases decide the form before the total does', () => {
	// 6-7-5 is a haiku with one extra sound, though 18 alone would be too.
	assert.equal(japaneseForm(18, [6, 7, 5])?.form, 'haiku-senryu');
	assert.equal(japaneseForm(26, [7, 7, 7, 5])?.form, 'dodoitsu');
	assert.equal(japaneseForm(38, [5, 7, 7, 5, 7, 7])?.form, 'sedoka');
	assert.equal(japaneseForm(38, [5, 7, 5, 7, 7, 7])?.form, 'bussokuseki');
	assert.equal(japaneseForm(43, [5, 7, 5, 7, 5, 7, 7])?.form, 'choka');
	// Phrases that are no form fall back to the total.
	assert.equal(japaneseForm(38, [20, 18])?.form, 'sedoka-bussokuseki');
	assert.equal(japaneseForm(52, [21, 31]), null);
});

test('English names a form by its lines, and by syllables where the form is made of them', () => {
	assert.equal(englishForm([10]), null);
	assert.equal(englishForm([8, 8])?.form, 'couplet');
	assert.equal(englishForm([5, 7, 5])?.form, 'haiku');
	assert.equal(englishForm([10, 10, 10])?.form, 'tercet');
	assert.equal(englishForm([2, 4, 6, 8, 2])?.form, 'cinquain');
	// A limerick's 8-8-5-5-8 is five lines but no cinquain.
	assert.equal(englishForm([8, 8, 5, 5, 8]), null);
	assert.equal(englishForm(Array(13).fill(10))?.form, 'sonnet');
	assert.equal(englishForm(Array(9).fill(10)), null);
	assert.equal(englishForm(Array(20).fill(8))?.form, 'villanelle');
	assert.equal(englishSyllables('An old silent pond'), 5);
});

test('the counts the Server made are used once they come, and the page estimates until then', () => {
	const haiku = '古池や\n蛙飛び込む\n水の音';
	// Seventeen sounds, eleven characters: the characters are no form.
	assert.deepEqual(describeLength(haiku, 'ja', ON), { unit: 'chars', count: 11, form: null });
	assert.deepEqual(describeLength(haiku, 'ja', ON, { mora: { mora: 17, phrases: [5, 7, 5], unread: [] } }),
		{ unit: 'mora', count: 17, form: { form: 'haiku-senryu', length: 17 }, approximate: false });
	const english = 'An old silent pond\nA frog jumps into the pond\nSplash! Silence again';
	assert.deepEqual(describeLength(english, 'ja', ON), { unit: 'lines', count: 3, form: { form: 'haiku', length: 3 } });
});

test('a language switched off is counted and not judged', () => {
	const off = { japanese: false, english: false };
	assert.deepEqual(describeLength('古池や\n蛙飛び込む\n水の音', 'ja', off, { mora: { mora: 17, phrases: [5, 7, 5], unread: [] } }),
		{ unit: 'chars', count: 11, form: null });
	assert.deepEqual(describeLength('An old pond\nA frog', 'ja', off), { unit: 'lines', count: 2, form: null });
});
