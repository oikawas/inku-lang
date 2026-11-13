// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { atName, lawName, placeName } from './composition-names.ts';
import { compositionOf, compositionShown, quoteInDescription, thesisOf, thingPlaces } from './record.ts';

// The shape of a saved read-and-draw work's record (the 11-06 work drawn from 大海の, abridged).
const USED = {
	state: 'used' as const,
	answer: {
		thesis: '広い海面から斜めに迫る波を磯際で大きく割る。',
		form: 'dividing_line',
		main_law: 'B1',
		laws: {
			B1: { targets: [{ at: 'point_lr', thing: 2 }, { at: 'point_ll', thing: 3 }] },
			B21: { targets: [{ hand: 'fine', thing: 1 }] },
			C1: { things: [4], spot: 'golden_ul' }
		},
		things: [{ thing: 1, what: '広い海面', role: 'field', kind: 'surface', quote: '大海の' }]
	}
};

test('only a used record shows its thesis; a fallback and a missing record read apart', () => {
	assert.equal(thesisOf(USED), USED.answer.thesis);
	assert.equal(thesisOf({ ...USED, state: 'fallback' }), null);
	assert.equal(compositionShown(USED).kind, 'used');
	assert.equal(compositionShown({ state: 'fallback', fallback: 'refused' }).kind, 'fallback');
	assert.equal(compositionShown(null).kind, 'none');
	assert.equal(compositionOf({ description_ddl: { composition: USED } }), USED);
	assert.equal(compositionOf({ description_ddl: null }), null);
	assert.equal(compositionOf(null), null);
});

test('a thing gets the place its law put it at, and a card\'s spot; a thing only shaped has none', () => {
	const places = thingPlaces(USED.answer, true);
	assert.equal(places.get(2), `${lawName('B1', true)}・${atName('point_lr', true)}`);
	assert.equal(places.get(3), `${lawName('B1', true)}・${atName('point_ll', true)}`);
	assert.equal(places.get(4), placeName('golden_ul', true));
	assert.equal(places.has(1), false);
	assert.equal(thingPlaces(null, true).size, 0);
});

test('a quote is in the description when its words are, spaces aside', () => {
	assert.equal(quoteInDescription('寄する波　割れて', '大海の　磯もとどろに　寄する波　割れて砕けて'), true);
	assert.equal(quoteInDescription('白い破片', '大海の　磯もとどろに'), false);
	assert.equal(quoteInDescription('', '大海の'), false);
});
