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
