// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Text } from '@codemirror/state';

import { LatestRequest, quoteSpan, readUnits, thingAt, thingBox, thingLines, thingOfLine } from './things.ts';
import { chunkLineDecorations } from '../ddl-editor/codemirror-chunks.ts';
import { captionParts, withHighlight } from '../../captionText.ts';

const ANSWER = {
	schema: 'inku.chunk-moves.v1',
	outcome: 'ok',
	units: [
		{ title: null, thing: null, lines: [0, 1], sentences: 2, unplaced: 2, box: null },
		{ title: '大海の', thing: 1, lines: [3, 4, 5], sentences: 2, unplaced: 0, box: [0.08, 0.2, 0.9, 0.45] },
		{ title: '磯もとどろに', thing: 2, lines: [6, 7], sentences: 1, unplaced: 0, box: [0.4, 0.4, 0.84, 0.82] },
		{ title: '白い破片', thing: 3, lines: [8, 9], sentences: 1, unplaced: 0, box: [0.5, 0.3, 0.6, 0.42] },
		{ title: '舟', thing: 4, lines: [10, 11], sentences: 1, unplaced: 1, box: null },
		{ title: 'bad', thing: 5, lines: [12], box: [0, 1] }
	]
};

test('the answer reads as units; a malformed box is no box', () => {
	const units = readUnits(ANSWER);
	assert.equal(units.length, 6);
	assert.deepEqual(units[1], { title: '大海の', thing: 1, lines: [3, 4, 5], box: [0.08, 0.2, 0.9, 0.45] });
	assert.equal(units[5].box, null);
	assert.deepEqual(readUnits({ units: 'no' }), []);
	assert.deepEqual(readUnits(null), []);
});

test('the point falls on the smallest box that holds it; a thing without a box is never pointed at on the drawing', () => {
	const units = readUnits(ANSWER);
	assert.equal(thingAt(units, 0.55, 0.41), 3);
	assert.equal(thingAt(units, 0.6, 0.6), 2);
	assert.equal(thingAt(units, 0.1, 0.9), null);
	assert.deepEqual(thingBox(units, 4), null);
	assert.deepEqual(thingLines(units, 4), [10, 11]);
	assert.equal(thingOfLine(units, 7), 2);
	assert.equal(thingOfLine(units, 0), null);
});

test('a quote lights its words in the caption, spaces aside', () => {
	const caption = '大海の　磯もとどろに　寄する波';
	assert.deepEqual(quoteSpan(caption, '磯もとどろに'), { start: 4, end: 10 });
	assert.deepEqual(quoteSpan(caption, '大海の 磯'), { start: 0, end: 5 });
	assert.equal(quoteSpan(caption, '白い破片'), null);
	const parts = withHighlight(captionParts('霧の[補足]朝'), { start: 0, end: 2 });
	assert.deepEqual(parts.map((part) => [part.text, !!part.lit, part.italic]), [['霧の', true, false], ['[補足]', false, true], ['朝', false, false]]);
});

test('only the latest request may set the units', () => {
	const requests = new LatestRequest();
	const first = requests.begin();
	const second = requests.begin();
	assert.equal(requests.current(first), false);
	assert.equal(requests.current(second), true);
	requests.reset();
	assert.equal(requests.current(second), false);
});

test('the pointed chunk lights its lines; lines past the end are skipped', () => {
	const doc = Text.of(['「大海の」', '画面の横0.1…', '「磯」', '…']);
	const set = chunkLineDecorations(doc, [2, 3, 9]);
	const starts: number[] = [];
	set.between(0, doc.length, (from) => { starts.push(from); });
	assert.deepEqual(starts, [doc.line(3).from, doc.line(4).from]);
});
