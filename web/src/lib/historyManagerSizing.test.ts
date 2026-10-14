import assert from 'node:assert/strict';
import { test } from 'node:test';
import { historyGridPageSize } from './historyManagerSizing.ts';

test('closing the preview keeps the third row when its actual height fits', () => {
	// Browser measurement: 12 columns, with a shorter middle row. Repeating the
	// tallest card for every row wrongly reduced this 36-work page to 24 works.
	const input = {
		width: 1868,
		height: 872,
		gap: 8,
		minCardWidth: 142,
		cardHeights: [
			...Array(12).fill(291.59375),
			...Array(12).fill(267.59375),
			...Array(12).fill(291.59375)
		]
	};
	assert.equal(historyGridPageSize(input), 36);
	// The same third row genuinely does not fit just below its measured end.
	assert.equal(historyGridPageSize({ ...input, height: 866 }), 24);
});
