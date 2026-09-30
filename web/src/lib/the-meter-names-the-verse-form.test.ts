// Run with: npm run test:unit  (node:test, no test dependency)
//
// The meter under the description names the verse form the description is
// nearest to. Japanese: haiku 17, katauta 19, tanka 31, sedōka and
// bussokuseki-ka 38, chōka 12n + 7 from 43, in sounds the Server counts, or in
// characters until it answers. English: by lines, couplet 2 to sestina 39.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { describeLength, englishSyllables, nearestEnglishForm, nearestVerseForm, verseFormOfSounds } from './verseForm.ts';

test('each form is named at its own length', () => {
	assert.deepEqual(nearestVerseForm(17), { form: 'haiku', length: 17 });
	assert.deepEqual(nearestVerseForm(19), { form: 'katauta', length: 19 });
	assert.deepEqual(nearestVerseForm(31), { form: 'tanka', length: 31 });
	// Sedōka and bussokuseki-ka are both 38: one name covers the two.
	assert.deepEqual(nearestVerseForm(38), { form: 'sedoka-bussokuseki', length: 38 });
	assert.deepEqual(nearestVerseForm(43), { form: 'choka', length: 43 });
	assert.deepEqual(nearestVerseForm(79), { form: 'choka', length: 79 });
});

test('a length between forms goes to the nearer, and a tie to the shorter', () => {
	assert.equal(nearestVerseForm(18).form, 'haiku');
	assert.equal(nearestVerseForm(25).form, 'katauta');
	assert.equal(nearestVerseForm(26).form, 'tanka');
	assert.equal(nearestVerseForm(40).form, 'sedoka-bussokuseki');
	assert.deepEqual(nearestVerseForm(41), { form: 'choka', length: 43 });
	assert.deepEqual(nearestVerseForm(50), { form: 'choka', length: 55 });
	assert.deepEqual(nearestVerseForm(0), { form: 'haiku', length: 17 });
});

test('at 38 the phrases tell sedōka from bussokuseki-ka, and otherwise both are named', () => {
	assert.equal(verseFormOfSounds(38, [5, 7, 7, 5, 7, 7]).form, 'sedoka');
	assert.equal(verseFormOfSounds(38, [5, 7, 5, 7, 7, 7]).form, 'bussokuseki');
	assert.equal(verseFormOfSounds(38, [38]).form, 'sedoka-bussokuseki');
	assert.equal(verseFormOfSounds(31, [5, 7, 5, 7, 7]).form, 'tanka');
});

test('the sounds the Server counted are used once they come, and characters until then', () => {
	// Seventeen sounds, eleven characters: the kanji are read as several sounds.
	const text = '古池や　蛙飛び込む\n水の音';
	assert.deepEqual(describeLength(text, 'ja'), { unit: 'chars', count: 11, target: 17, form: 'haiku', over: false });
	assert.deepEqual(describeLength(text, 'ja', { mora: 17, phrases: [5, 7, 5], unread: [] }),
		{ unit: 'mora', count: 17, target: 17, form: 'haiku', approximate: false, over: false });
	// A character the dictionary could not read makes the count approximate.
	assert.deepEqual(describeLength('濡', 'ja', { mora: 2, phrases: [2], unread: ['濡'] }),
		{ unit: 'mora', count: 2, target: 17, form: 'haiku', approximate: true, over: false });
});

test('English is counted in lines, and three short lines are a haiku', () => {
	const haiku = ['An old silent pond', 'A frog jumps into the pond', 'Splash! Silence again'];
	assert.equal(englishSyllables(haiku.join(' ')), 17);
	assert.deepEqual(nearestEnglishForm(haiku), { form: 'haiku', length: 3 });
	const tercet = ['The river kept its promise to the valley every spring', 'until the year the snows forgot to come at all', 'and then the valley learned to keep its own'];
	assert.deepEqual(nearestEnglishForm(tercet), { form: 'tercet', length: 3 });
	assert.equal(nearestEnglishForm(Array(14).fill('line')).form, 'sonnet');
	assert.equal(nearestEnglishForm(Array(18).fill('line')).form, 'villanelle');
	assert.equal(nearestEnglishForm(['one line']).form, 'couplet');
	assert.deepEqual(describeLength(haiku.join('\n'), 'ja'), { unit: 'lines', count: 3, target: 3, form: 'haiku', over: false });
});
