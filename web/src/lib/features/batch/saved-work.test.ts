import assert from 'node:assert/strict';
import { test } from 'node:test';
import { loadBatchSavedWork } from './saved-work.ts';

test('loads the exact saved work without the history strip filters', async () => {
	const calls: string[] = [];
	const item = { id: 'saved work', input: 'test data', ddl: '', score: { instructions: [] }, svg: '', at: 1,
		draw_options: { route: 'read_and_draw', sketch: 'on', composition: 'on', wild: 'off',
			catalog: null, canvas_aspect: null, models: null } };
	const found = await loadBatchSavedWork(async (path) => { calls.push(path); return Response.json({ items: [item] }); }, item.id);
	assert.deepEqual(found, item);
	const query = new URL(calls[0], 'http://example.test').searchParams;
	assert.equal(query.get('anchor_id'), item.id);
	assert.equal(query.get('limit'), '1');
	assert.equal(query.has('starred'), false);
});

test('does not substitute another work when the saved id is absent', async () => {
	await assert.rejects(loadBatchSavedWork(async () => Response.json({ items: [{ id: 'other' }] }), 'missing'));
});
