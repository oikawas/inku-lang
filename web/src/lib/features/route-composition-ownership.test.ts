import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = (path: string): string => {
	try { return readFileSync(new URL(path, import.meta.url), 'utf8'); }
	catch { return ''; }
};

test('T-1001/T-1005: the route constructs the Session owner once', () => {
	const page = read('../../routes/+page.svelte');
	assert.match(page, /import \{ createSessionState,[^}]+\} from '\$lib\/features\/session\/state\.svelte';/);
	assert.equal((page.match(/createSessionState\(/g) ?? []).length, 1);
});

test('T-1001/T-1006: Session writers no longer remain on the route', () => {
	const page = read('../../routes/+page.svelte');
	const session = read('./session/state.svelte.ts');

	for (const writer of ['login', 'logout', 'saveProfile', 'updateUiMode']) {
		assert.match(session, new RegExp(`(?:async )?${writer}\\(`), writer);
		assert.doesNotMatch(page, new RegExp(`(?:async )?function ${writer}\\(`), writer);
	}
	assert.match(session, /currentUser = \$state<UserItem \| null>/);
	assert.doesNotMatch(page, /let currentUser(?:\s*:[^=]+)?\s*=\s*\$state/);
});

test('T-1001/T-1005: the route constructs the Work owner once', () => {
	const page = read('../../routes/+page.svelte');
	assert.match(page, /import \{ createWorkState \} from '\$lib\/features\/work\/state\.svelte';/);
	assert.equal((page.match(/createWorkState\(/g) ?? []).length, 1);
});

test('T-1001/T-1004: submit, replay, and stop have one Work owner', () => {
	const page = read('../../routes/+page.svelte');
	const work = read('./work/state.svelte.ts');
	for (const writer of ['submit', 'replay', 'stopDdlRender']) {
		assert.match(work, new RegExp(`(?:async\\s+)?function\\s+${writer}\\(`), writer);
		assert.doesNotMatch(page, new RegExp(`(?:async )?function ${writer}\\(`), writer);
	}
	for (const state of ['input', 'ddl', 'result', 'loading', 'displayedHistoryItem']) {
		assert.match(work, new RegExp(`${state}\\s*=\\s*\\$state`), state);
		assert.doesNotMatch(page, new RegExp(`let ${state}(?:\\s*:[^=]+)?\\s*=\\s*\\$state`), state);
	}
});
