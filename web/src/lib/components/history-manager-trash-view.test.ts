import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

/**
 * The trash view must not offer the buttons that make something out of a work.
 *
 * The server refuses a trashed id on those routes (ledger I-094), so a visible
 * button there can only produce a 404. There is no component-rendering harness
 * in this project -- `test:unit` is `node --test` with no DOM -- so this reads
 * the source and checks that each button sits inside a block conditioned on the
 * active view. It cannot see what a browser paints; it can see the guard being
 * removed or a button being moved out from under it.
 */

const SOURCE = fileURLToPath(new URL('./HistoryManager.svelte', import.meta.url));

/** The labels of the buttons that turn selected works into a file. */
const WORK_TOOLS = [
	't().historyContactSheet}',
	't().historyContactSheetAi}',
	't().historyAnimationExport}',
];

const ACTIVE_VIEW_GUARD = "historyManagerView === 'active'";

/**
 * Conditions the given line (1-based) is reached under.
 *
 * `{:else}` matters here: the restore and delete buttons live in the else of
 * the very guard the tools are wrapped in, so a walk that only counted
 * {#if}/{/if} would report them as guarded by it. An else branch is recorded as
 * the negated condition instead.
 */
function openBlocksAt(text: string, line: number): string[] {
	const stack: { condition: string; inElse: boolean }[] = [];
	for (const current of text.split('\n').slice(0, line)) {
		for (const match of current.matchAll(/\{#(if|each)\b([^}]*)\}/g)) {
			stack.push({ condition: match[2].trim(), inElse: false });
		}
		for (const match of current.matchAll(/\{:else\b([^}]*)\}/g)) {
			const top = stack[stack.length - 1];
			if (top) {
				top.inElse = true;
				const elseIf = match[1].replace(/^\s*if\b/, '').trim();
				if (elseIf) top.condition = elseIf;
			}
		}
		for (const _ of current.matchAll(/\{\/(if|each)\}/g)) stack.pop();
	}
	return stack.map((entry) => (entry.inElse ? `!(${entry.condition})` : entry.condition));
}

test('the work tools sit behind the active-view guard', () => {
	const text = readFileSync(SOURCE, 'utf8');
	const lines = text.split('\n');
	for (const tool of WORK_TOOLS) {
		const index = lines.findIndex((line) => line.includes(tool));
		assert.notEqual(index, -1, `button not found in the source: ${tool}`);
		const guards = openBlocksAt(text, index + 1);
		assert.ok(
			guards.includes(ACTIVE_VIEW_GUARD),
			`${tool} is reachable in the trash view; open blocks were ${JSON.stringify(guards)}`,
		);
	}
});

test('restore and permanent delete stay out of the active-view guard', () => {
	// The control: the two buttons the trash view exists for must NOT be behind
	// it, or the test above would pass by everything being hidden everywhere.
	const text = readFileSync(SOURCE, 'utf8');
	const lines = text.split('\n');
	for (const label of ['t().historyRestoreSelected}', 't().historyPermanentDelete}']) {
		const index = lines.findIndex((line) => line.includes(label));
		assert.notEqual(index, -1, `button not found in the source: ${label}`);
		const guards = openBlocksAt(text, index + 1);
		assert.ok(
			!guards.includes(ACTIVE_VIEW_GUARD),
			`${label} would be hidden in the trash view; open blocks were ${JSON.stringify(guards)}`,
		);
	}
});
