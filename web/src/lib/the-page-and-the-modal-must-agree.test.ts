// Run with: npm run test:unit  (node:test, no test dependency)
//
// Contract 2, stage 7. Two places decide how many works one manager page holds:
// the page guesses from the window before the modal exists (65 measured), and
// the modal measures its own grid once it is on screen (52 measured). Contract 1
// stopped the disagreement from costing a second fetch, but left the two numbers
// in use at once -- 65 works drawn, `offset` advancing by 52 -- so the next page
// handed back 13 works the first page had already been given.
//
// What makes that worse than a duplicate: the grid's box is overflow: hidden
// (HistoryManager.svelte:1054, no scrollbar), so the works past the box are not
// seen at all. Paging by the larger number instead would step over them.
//
// These gates drive the real HistoryManagerState against a server that answers
// by offset, so nothing here can be satisfied by a rewritten condition.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
	HistoryManagerState,
	MANAGER_PAGE_SIZE,
	MEASURED_PAGE_SIZE,
	STRIP_SIZE,
	TOTAL,
	refreshDerived,
	works
} from './history-manager-harness.ts';

/** Every work the server has, in list order, so a page can be located in it. */
const CORPUS = works(TOTAL, 'work');

/** A manager whose server answers each request from CORPUS by offset and limit. */
function makeCorpusManager() {
	const calls: string[] = [];
	const apiFetch = async (path: string) => {
		calls.push(path);
		const asked = new URL(path, 'http://localhost');
		const offset = Number(asked.searchParams.get('offset'));
		const limit = Number(asked.searchParams.get('limit'));
		return {
			ok: true,
			json: async () => ({ items: CORPUS.slice(offset, offset + limit), total: TOTAL })
		} as unknown as Response;
	};
	const manager = new HistoryManagerState(apiFetch, () => {});
	return { manager, calls };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

/**
 * The sequence one press actually produces, measured in the browser on
 * 28ce4237: the page seeds the strip and opens with its guess, the modal comes
 * up and reports what it measured, then the guessed page arrives.
 */
async function openTheManager() {
	const { manager, calls } = makeCorpusManager();
	manager.seedFromStrip(CORPUS.slice(0, STRIP_SIZE), TOTAL, 6, MANAGER_PAGE_SIZE);
	refreshDerived(manager);
	manager.openWith(CORPUS.slice(0, STRIP_SIZE), TOTAL, 6);
	manager.setPageSize(MEASURED_PAGE_SIZE);
	await settle();
	refreshDerived(manager);
	return { manager, calls };
}

// ── T-17 ────────────────────────────────────────────────────────────────────
test('the second page starts where the first one ended -- no overlap, no gap', async () => {
	// Stated first: the gate is worthless if the two numbers are written equal,
	// because then paging by either one lands in the same place and P-14 walks
	// straight through.
	assert.notEqual(MANAGER_PAGE_SIZE, MEASURED_PAGE_SIZE);

	const { manager } = await openTheManager();
	const firstPage = manager.items.map((it) => it.id);
	assert.ok(firstPage.length > 0);

	manager.setPage(1);
	await settle();
	refreshDerived(manager);
	const secondPage = manager.items.map((it) => it.id);
	assert.ok(secondPage.length > 0);

	// One statement covers both faults: any work shown twice makes the joined
	// list longer than the corpus prefix, any work stepped over makes it differ.
	assert.deepEqual(
		[...firstPage, ...secondPage],
		CORPUS.slice(0, firstPage.length + secondPage.length).map((it) => it.id)
	);
});

// ── T-18 ────────────────────────────────────────────────────────────────────
test('one press is still one request', async () => {
	const { manager, calls } = await openTheManager();
	assert.equal(calls.length, 1);

	// The modal does not always report while the page is still on its way: it
	// mounts about 888 ms after the click, by which time the answer can already
	// have landed. Reporting then finds nothing in flight to ride on, so an
	// implementation that fixed stage 7 by re-fetching would send a second page
	// here and nowhere else. Measured before the fix: with the guessed page in
	// hand, this is exactly the moment the manager decided it was short.
	manager.setPageSize(MEASURED_PAGE_SIZE);
	await settle();
	assert.equal(calls.length, 1);
});
