import assert from 'node:assert/strict';
import { test } from 'node:test';

import { snapshotSavedWorkExport } from './saved-work.ts';

test('saved-work snapshot sorts a selection but preserves the supplied lineage path order', () => {
	const selection = snapshotSavedWorkExport({
		kind: 'selection',
		works: [
			{ id: 'newer', at: 30 },
			{ id: 'older', at: 10 },
			{ id: 'middle', at: 20 },
		],
	});
	const path = snapshotSavedWorkExport({
		kind: 'lineage-path',
		works: [
			{ id: 'ancestor', at: 30 },
			{ id: 'parent', at: 20 },
			{ id: 'child', at: 10 },
		],
	});

	assert.deepEqual(selection?.ids, ['older', 'middle', 'newer']);
	assert.deepEqual(path?.ids, ['ancestor', 'parent', 'child']);
});

test('saved-work snapshot rejects an unavailable target rather than exporting a subset', () => {
	assert.equal(snapshotSavedWorkExport({
		kind: 'selection',
		works: [
			{ id: 'available', at: 10 },
			{ id: 'trashed', at: 20, trashed: true },
			{ id: 'unavailable', at: 30, unavailable: true },
		],
	}), null);
	assert.equal(snapshotSavedWorkExport({
		kind: 'selection',
		works: [
			{ id: 'duplicate', at: 10 },
			{ id: 'duplicate', at: 20 },
		],
	}), null);
});
