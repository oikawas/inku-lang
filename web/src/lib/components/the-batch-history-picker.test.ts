import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

/**
 * T-58 and T-59: how many past batches are kept, and the list that shows them.
 *
 * There is no component-rendering harness in this project -- `test:unit` is
 * `node --test` with no DOM -- so the parts that only exist on screen are read
 * from the source.
 */

const PANEL = readFileSync(fileURLToPath(new URL('./BatchPanel.svelte', import.meta.url)), 'utf8');
const OWNER = readFileSync(fileURLToPath(new URL('../features/batch/state.svelte.ts', import.meta.url)), 'utf8');
const SERVER_SETTINGS = readFileSync(
	fileURLToPath(new URL('../../../../server/src/inku_server/persistence/settings.py', import.meta.url)),
	'utf8',
);

test('T-58  both ends of the batch history keep the same number of prompts', () => {
	// The server cuts the list on the read and on the write, so the shorter of
	// the two numbers is what the picker shows. Raising one alone changes
	// nothing, and the failure is silent: the picker simply stays as it was.
	const web = OWNER.match(/const BATCH_PROMPT_HISTORY_LIMIT = (\d+);/);
	const server = SERVER_SETTINGS.match(/^BATCH_PROMPT_HISTORY_LIMIT = (\d+)$/m);
	assert.ok(web, 'the web client no longer names a batch history limit');
	assert.ok(server, 'the server no longer names a batch history limit');
	// Written down here rather than compared to each other: two constants read
	// from the same place agree with themselves whatever they say.
	assert.equal(web[1], '50');
	assert.equal(server[1], '50');
});

test('T-59  the picker is a bounded list, not a native dropdown', () => {
	// How tall a <select> opens is the browser's to decide; the ceiling the
	// author asked for can only be set on a list of our own.
	assert.doesNotMatch(PANEL, /<select/, 'the batch history picker is a native <select> again');
	assert.match(PANEL, /class="batch-history-menu" role="listbox"/, 'the picker is not a listbox');
	const menu = PANEL.match(/\.batch-history-menu \{[\s\S]*?\n\t\}/);
	assert.ok(menu, 'the menu has no style block');
	assert.match(menu[0], /max-height: 50vh;/, 'the list is not bounded to half the window');
	assert.match(menu[0], /overflow: auto;/, 'a list past the ceiling cannot be scrolled');
});

test('T-59  the list closes on a press outside it and on Escape', () => {
	assert.match(PANEL, /onclick=\{closeHistoryMenuOnOutsideClick\}/, 'a press outside no longer closes the list');
	assert.match(PANEL, /event\.key === 'Escape'/, 'Escape no longer closes the list');
	// A menu of our own has no browser dismissing it; without these it stays
	// open over the box it is meant to fill.
	assert.match(PANEL, /historyMenuWrapEl\?\.contains\(event\.target as Node\)/, 'a press inside the list closes it');
});
