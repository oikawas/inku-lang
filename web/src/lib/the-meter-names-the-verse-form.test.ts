// Run with: npm run test:unit  (node:test, no test dependency)
//
// The meter under the description names the verse form the description's
// length is nearest to: haiku 17, katauta 19, tanka 31, sedōka and
// bussokuseki-ka 38, chōka 12n + 7 from 43. It counts characters, not sounds.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { describeLength, nearestVerseForm } from './verseForm.ts';

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

test('the meter counts the description the drawing reads, without white space', () => {
	// Seventeen sounds, eleven characters: the kanji are read as several sounds.
	const haiku = describeLength('古池や　蛙飛び込む\n水の音', 'ja');
	assert.deepEqual(haiku, { unit: 'chars', count: 11, target: 17, form: 'haiku', over: false });
	assert.deepEqual(describeLength('A pond, a frog, the sound of water', 'ja'),
		{ unit: 'words', count: 8, target: 12, over: false });
});
