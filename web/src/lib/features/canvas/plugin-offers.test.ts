import assert from 'node:assert/strict';
import { test } from 'node:test';
import { offerName } from './plugin-offers';

test('offer names preserve a bare identifier when no saved name exists', () => {
	const item = { qualified_name: 'Nature.YoungLeaves', reason: 'name' as const };
	assert.equal(offerName(item, true), 'Nature.YoungLeaves');
	assert.equal(offerName({ ...item, written_en: '{young leaves}' }, false), '{young leaves}');
});
