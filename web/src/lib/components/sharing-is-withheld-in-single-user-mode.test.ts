import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

/**
 * T-15 and T-20 for the web: the share affordance, and the two labels.
 *
 * There is no component-rendering harness in this project -- `test:unit` is
 * `node --test` with no DOM -- so these read the source. That cannot see what a
 * browser paints, but it can see a condition being dropped or a label being
 * collapsed into one, which is the failure being guarded against in both cases.
 */

const PAGE = fileURLToPath(new URL('../../routes/+page.svelte', import.meta.url));
const MANAGER = fileURLToPath(new URL('./HistoryManager.svelte', import.meta.url));
const LINEAGE = fileURLToPath(new URL('./LineagePanel.svelte', import.meta.url));

const page = readFileSync(PAGE, 'utf8');
const manager = readFileSync(MANAGER, 'utf8');
const lineage = readFileSync(LINEAGE, 'utf8');

test('T-15 control: single-user mode is what withholds the share affordance', () => {
	// The handler is passed as null there, so the button below has nothing to
	// call and does not render. Passing it unconditionally would put a Share
	// button on a server where there is nobody to share with.
	assert.match(
		page,
		/onShareItem=\{singleUserMode \? null : /,
		'the share handler no longer depends on single-user mode',
	);
});

test('T-15: the share button renders only when there is a handler', () => {
	const guarded = manager.match(/\{#if historyManagerView === 'active' && onShareItem && !it\.shared\}/);
	assert.ok(guarded, 'the share button is not behind the onShareItem guard');

	// And it is offered on one's own works only: sharing what somebody shared
	// with you is not yours to do, and the server refuses it with a 404.
	assert.match(manager, /&& !it\.shared\}/, 'the button is offered on works that are not the caller’s');
});

test('a work reached through someone else’s permission is marked as such', () => {
	assert.match(manager, /class="shared-mark"/, 'the shared mark is gone');
	assert.match(manager, /\{#if it\.shared\}/, 'the mark no longer depends on the field');
});

test('T-20: deleted and withheld carry different words, in both languages', () => {
	const helper = lineage.match(/function withheldLabel[\s\S]*?\n\t\}/);
	assert.ok(helper, 'the label helper is gone');
	const body = helper[0];

	assert.match(body, /not_permitted[\s\S]*?'非公開' : 'Private'/, 'no withheld label');
	assert.match(body, /'削除済み' : 'Deleted'/, 'no deleted label');

	// The point of the ruling: one word for both would tell someone to stop
	// asking for a work whose owner could still hand it over.
	const ja = body.match(/'([^']+)' : 'Private'/)?.[1];
	const jaDeleted = body.match(/'([^']+)' : 'Deleted'/)?.[1];
	assert.notEqual(ja, jaDeleted, 'the Japanese labels are the same word');
	assert.ok(body.indexOf('not_permitted') < body.indexOf("'Deleted'"),
		'the withheld case must be tested before the tombstone case, or it never fires');
});

test('T-20: a withheld node is drawn like a tombstone, dashed card and arrow', () => {
	assert.match(
		lineage,
		/class:tombstone=\{node\.state === 'tombstone' \|\| node\.redacted === 'not_permitted'\}/,
		'a withheld node renders as an ordinary empty card',
	);
	assert.match(
		lineage,
		/n\?\.state === 'tombstone' \|\| n\?\.redacted === 'not_permitted'/,
		'the arrow into a withheld node is not dashed',
	);
});
