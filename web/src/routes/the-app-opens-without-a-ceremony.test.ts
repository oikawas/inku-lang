// Run with: npm run test:unit  (node:test, no test dependency)
//
// Single-user mode drops the doors that lead nowhere and keeps the one that
// leads back.  Signing out is pointless on a server that signs you straight
// back in; changing the password is not, because single-user mode makes an
// account nobody knows a password for, and that password is the only way to
// sign in again once the mode is turned off.
//
// Both halves read the source rather than rendering it: these are Svelte 5
// components with runes, and node cannot import them without the compiler.
// So each check cuts out the region it is about first -- asserting over a
// whole file would let an unrelated occurrence of the same guard satisfy it.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

const ROUTES_DIR = dirname(fileURLToPath(import.meta.url));
const COMPONENTS_DIR = join(ROUTES_DIR, '..', 'lib', 'components');

function read(path: string): string {
	return readFileSync(path, 'utf8');
}

/** The text between two markers, so a check cannot be satisfied elsewhere. */
function region(source: string, open: string, close: string): string {
	const start = source.indexOf(open);
	assert.notEqual(start, -1, `region opener not found: ${open}`);
	const end = source.indexOf(close, start + open.length);
	assert.notEqual(end, -1, `region closer not found: ${close}`);
	return source.slice(start, end);
}

test('the rail hides signing out when the server signs you in by itself', () => {
	const menu = region(read(join(COMPONENTS_DIR, 'AppRail.svelte')), '<div class="rail-user-menu"', '</div>');
	assert.match(menu, /onclick=\{onLogout\}/, 'the sign-out button should still exist');
	assert.match(menu, /\{#if !singleUserMode\}/, 'sign-out should be behind the single-user gate');
});

test('the settings panel hides signing out but keeps the way back', () => {
	const source = read(join(ROUTES_DIR, '..', 'lib', 'features', 'settings', 'UserAdministrationSettings.svelte'));
	const sessionRow = region(source, '<div class="user-session-row">', '{/if}\n');
	assert.match(sessionRow, /\{#if !singleUserMode\}/, 'sign-out should be behind the single-user gate');

	// The control: the profile panel changes the password, and single-user
	// mode must not touch it.  A gate here would strand every work the single
	// user made behind an account whose password nobody knows.
	const profile = region(
		read(join(COMPONENTS_DIR, 'ProfileModal.svelte')),
		'profileNewPasswordLabel',
		'profileSaveButton'
	);
	assert.doesNotMatch(profile, /singleUserMode/, 'the password field must not be gated on single-user mode');
});
