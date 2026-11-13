import assert from 'node:assert/strict';
import test from 'node:test';
import { HistoryManagerState, works } from './history-manager-harness.ts';
import { descriptionColumns, workComposition } from './features/library/description-columns.ts';
import { formIds } from './features/composition-record/composition-names.ts';

test('description mode opens without a chronological listing request', async () => {
	const requests: string[] = [];
	const manager = new HistoryManagerState(async (path) => { requests.push(path); return new Response('{}'); }, () => {});
	manager.setDisplayMode('description');
	manager.openWith(works(10), 10, 0, null);
	await manager.fetch();
	assert.deepEqual(requests, []);
});

const used = (form: string, mainLaw: string) => ({ description_ddl: { composition: { state: 'used', answer: { form, main_law: mainLaw } } } });

test('a description\'s works stand in form columns in table order, a child in its ancestor\'s column, no record last', () => {
	const [first, second] = formIds().filter((form) => form !== 'grid').slice(0, 2);
	const items = [
		{ id: 'c', at: 3, ...used(second, 'B1') },
		{ id: 'a', at: 2, ...used(first, 'B6') },
		{ id: 'n', at: 1, description_ddl: null },
		{ id: 'k', at: 4, composition_inherited: { history_id: 'a', at: 2, via: ['tool_change'], answer: { form: first, main_law: 'B6' } } },
		{ id: 'z', at: 0, ...used('a_form_from_a_newer_core', 'B1') }
	];
	const columns = descriptionColumns(items);
	assert.deepEqual(columns.map((column) => column.form), [first, second, 'a_form_from_a_newer_core', null]);
	assert.deepEqual(columns[0].items.map((item) => item.id), ['a', 'k']);
	assert.deepEqual(workComposition(items[3]), { form: first, mainLaw: 'B6', inheritedVia: 'tool_change' });
	assert.deepEqual(workComposition(items[2]), { form: null, mainLaw: null, inheritedVia: null });
});
