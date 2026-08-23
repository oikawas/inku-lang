// Run with: npm run test:unit  (node:test, no test dependency)
//
// T-87 / T-88: signing in reads the two lists that stopped being public.
//
// I-086 moved /api/color-catalogs and /api/prompts behind the authorization
// guard. The startup fetch runs before anyone has logged in, so both now come
// back 401 there and the page swallows it; unless `login()` asks again, the
// catalog stays on FALLBACK_CATALOG and the Prompt tab stays empty until the
// page is reloaded.
//
// The check is cut down to the body of `login()` before it is matched. The page
// calls both functions in several places -- `loadCurrentUser()` alone has the
// same list one function above -- so a match against the whole file, or even
// against a generous slice, would be satisfied by an occurrence that has
// nothing to do with signing in. T-88 below is the control that says the cut
// actually happened.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

const ROUTES_DIR = dirname(fileURLToPath(import.meta.url));
const PAGE = readFileSync(join(ROUTES_DIR, '+page.svelte'), 'utf8');
const SESSION = readFileSync(join(ROUTES_DIR, '..', 'lib', 'features', 'session', 'state.svelte.ts'), 'utf8');

/** The text between two markers, so a check cannot be satisfied elsewhere. */
function region(source: string, open: string, close: string): string {
	const start = source.indexOf(open);
	assert.notEqual(start, -1, `region opener not found: ${open}`);
	const end = source.indexOf(close, start + open.length);
	assert.notEqual(end, -1, `region closer not found: ${close}`);
	return source.slice(start, end);
}

/** The body of `login()`, from its declaration to the one that follows it. */
function loginBody(): string {
	return region(SESSION, 'async login()', 'async logout()');
}

test('signing in reads the catalog list and the prompts', () => {
	const login = loginBody();
	const afterAuthentication = region(PAGE, "async function completeAuthentication(source: 'resume' | 'login')", 'function resetAfterSignedOut()');
	assert.match(login, /afterAuthenticated\('login'\)/, 'login() should invoke its post-authentication boundary');
	assert.match(afterAuthentication, /source === 'login' \? \[loadColorCatalogs\(\), fetchPrompts\(\)\] : \[\]/, 'login should read the protected catalog and prompt lists');
});

test('the cut is a cut: login()s region is not the file and not its neighbour', () => {
	// The control for the check above. Without it, a `region` that silently
	// returned the whole file -- or that ran to the end of the script block --
	// would keep the first test green against a page where signing in never
	// asks for either list.
	const body = loginBody();

	assert.ok(body.length < SESSION.length / 4, 'the region should be a small part of Session');
	assert.ok(body.includes('loginPassword'), 'the region should be the sign-in code');

	// The neighbouring function has the same call list one function above, and
	// `downloadCurrentCard` is where perturbation P-10 moves the call to. Neither
	// body may be inside the region, or the first test is measuring the page.
	assert.doesNotMatch(body, /async loadCurrentUser\(/);
	assert.doesNotMatch(body, /async function downloadCurrentCard\(/);
	assert.doesNotMatch(body, /async logout\(/);
});
