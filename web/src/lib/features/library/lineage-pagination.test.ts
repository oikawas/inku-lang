import assert from 'node:assert/strict';
import test from 'node:test';
import { lineageArrowTarget, visibleLineageCount } from './lineage-pagination.ts';

test('lineage starts with 200 and arrow movement reveals the next 200', () => {
	assert.equal(visibleLineageCount(undefined), 200);
	assert.deepEqual(lineageArrowTarget(198, 2000, 200, 'ArrowRight'), { index: 199, shown: 200 });
	assert.deepEqual(lineageArrowTarget(199, 2000, 200, 'ArrowRight'), { index: 200, shown: 400 });
	assert.deepEqual(lineageArrowTarget(200, 2000, 400, 'ArrowLeft'), { index: 199, shown: 400 });
	assert.equal(lineageArrowTarget(0, 2000, 200, 'ArrowLeft'), null);
});
