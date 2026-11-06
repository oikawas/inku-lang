import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { LINEAGE_CHUNK_SIZE, visibleLineageCount } from './lineage-pagination.ts';

test('lineage starts with 200 and retains the expanded count', () => {
	assert.equal(visibleLineageCount(undefined), 200);
	assert.equal(LINEAGE_CHUNK_SIZE, 200);
	assert.equal(visibleLineageCount(400), 400);
});

test('lineage members do not handle arrow navigation', () => {
	const source = readFileSync(new URL('../../components/HistoryManager.svelte', import.meta.url), 'utf8');
	assert.doesNotMatch(source, /handleLineageArrow|lineageArrowTarget/);
	assert.match(source, /visibleLineageItems\(group\)/);
	assert.match(source, /showMoreLineage\(group\.root_node_id\)/);
});
