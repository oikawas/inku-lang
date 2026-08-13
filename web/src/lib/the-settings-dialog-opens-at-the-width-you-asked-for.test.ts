// Run with: npm run test:unit  (node:test, no test dependency)
//
// Acceptance for the settings dialog's standard / detailed mode.
//
// The dialog had grown ten tabs and handed all of them to everyone who could
// reach them, so a member who came to change one thing read a bar of ten
// choices to find it. Four of those tabs -- plugins, other (server), limits and
// the unread-word ledger -- answer questions you only have when you are tending
// the server, and the switch in the dialog's head is what asks for them.
//
// The load-bearing claim is that the bar and the guard cannot drift apart: the
// bar hiding a tab the guard still allowed would leave a body nothing reaches,
// and a button the guard refuses does nothing when pressed. Both read the same
// list, and T-46/T-49 execute that from the two ends.
//
// T-46 (which four tabs are detail-only), T-47 (the modes differ, and only in
// those four), T-48 (the page passes both gates), T-49 (the bar hides what the
// guard refuses), T-50 (the tab it falls back to can never be hidden),
// T-51 (narrowing the dialog moves off a tab that has just gone), T-52 (the
// switch is in the head, and the stored preference is read through the
// normaliser).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { ADMIN_ONLY_SETTINGS_TABS, canAccessSettingsTab } from './permissionGroups.ts';
import {
	DETAILED_ONLY_SETTINGS_TABS,
	isDetailedOnlySettingsTab,
	normalizeSettingsDetail,
	settingsTabShownAtDetail
} from './settingsDetail.ts';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const MODAL = read('./components/SettingsModal.svelte');
const PAGE = read('../routes/+page.svelte');

/** Every tab the settings bar can carry, in the order it draws them. */
const ALL_TABS = [
	'models',
	'plugins',
	'users',
	'db',
	'server_misc',
	'logs',
	'limits',
	'unread',
	'export',
	'misc'
];

/** The settings tab bar, without the model picker's own bar above it. */
const BAR = MODAL.slice(
	MODAL.indexOf('<div class="settings-tabs">'),
	MODAL.indexOf('<div class="settings-body">')
);

/** The dialog's head, up to the first tab bar. */
const HEAD = MODAL.slice(
	MODAL.indexOf('<div class="modal-head">'),
	MODAL.indexOf('<div class="settings-tabs')
);

// ------------------------------------------------------------------- T-46

test('T-46  the detailed mode is what adds exactly those four tabs', () => {
	assert.deepEqual([...DETAILED_ONLY_SETTINGS_TABS], ['plugins', 'server_misc', 'limits', 'unread']);
	// Both directions, so neither a fifth entry nor a missing one passes.
	for (const tab of DETAILED_ONLY_SETTINGS_TABS) {
		assert.equal(isDetailedOnlySettingsTab(tab), true, tab);
	}
	for (const tab of ALL_TABS.filter((tab) => !(DETAILED_ONLY_SETTINGS_TABS as readonly string[]).includes(tab))) {
		assert.equal(isDetailedOnlySettingsTab(tab), false, tab);
	}
});

test('T-46  the four are named for what they are, not for who may see them', () => {
	// Three of the four are already behind the administrators group; `plugins`
	// and `unread` are not. The two questions are separate, and an
	// implementation that had quietly folded this one into the permission list
	// would answer differently here.
	const admin = ADMIN_ONLY_SETTINGS_TABS as readonly string[];
	assert.equal(admin.includes('plugins'), false);
	assert.equal(admin.includes('unread'), false);
	assert.equal(admin.includes('limits'), false);
	assert.equal(admin.includes('server_misc'), true);
});

// ------------------------------------------------------------------- T-47

test('T-47  the standard mode hides those four and nothing else', () => {
	for (const tab of ALL_TABS) {
		const hidden = (DETAILED_ONLY_SETTINGS_TABS as readonly string[]).includes(tab);
		assert.equal(settingsTabShownAtDetail(tab, 'standard'), !hidden, tab);
	}
});

test('T-47  the detailed mode hides none of them', () => {
	// The control for the check above: an implementation that answered `false`
	// for the four whatever the mode would pass that one and fail this.
	for (const tab of ALL_TABS) {
		assert.equal(settingsTabShownAtDetail(tab, 'detailed'), true, tab);
	}
});

// ------------------------------------------------------------------- T-48

test('T-48  the page asks both gates, and still asks the old one unchanged', () => {
	assert.match(PAGE, /from '\$lib\/settingsDetail'/);
	// The permission call is untouched -- the two gates compose rather than one
	// swallowing the other, so a member outside the administrators group cannot
	// reach an administrator tab by turning the switch on.
	assert.match(
		PAGE,
		/canAccessSettingsTabFor\(tab, currentUser\) && settingsTabShownAtDetail\(tab, settingsDetail\)/
	);
	assert.equal(canAccessSettingsTab('server_misc', { permission_groups: ['users'] }), false);
});

// ------------------------------------------------------------------- T-49

test('T-49  the bar hides exactly the tabs the guard refuses', () => {
	const guarded = [...BAR.matchAll(/showsTab\('([a-z_]+)'\)/g)].map((match) => match[1]);
	// Both directions again, this time between the bar and the list: a fifth
	// button wrapped in the guard, or one of the four left unwrapped, fails.
	assert.deepEqual([...guarded].sort(), [...DETAILED_ONLY_SETTINGS_TABS].sort());
	for (const tab of guarded) {
		assert.match(BAR, new RegExp(`showsTab\\('${tab}'\\)\\}\\s*\\n\\s*<button[^>]*settingsTab === '${tab}'`));
	}
});

test('T-49  and it asks that question from the same module the page does', () => {
	// Not a copy of the four names: a bar with its own list would drift the
	// first time the list changed, and both ends would still be green.
	assert.match(MODAL, /from '\$lib\/settingsDetail'/);
	assert.match(MODAL, /settingsTabShownAtDetail\(tab, settingsDetail\)/);
	assert.doesNotMatch(BAR, /'server_misc', 'limits'/);
});

// ------------------------------------------------------------------- T-50

test('T-50  the tab the dialog falls back to is one no gate can hide', () => {
	// A member outside the administrators group would otherwise land on
	// `plugins`, which the standard mode has just taken away, and read an empty
	// dialog. The fallback has to be a tab that both gates always allow.
	assert.equal(isDetailedOnlySettingsTab('export'), false);
	assert.equal((ADMIN_ONLY_SETTINGS_TABS as readonly string[]).includes('export'), false);
	assert.equal(canAccessSettingsTab('export', { permission_groups: ['users'] }), true);
	assert.equal(settingsTabShownAtDetail('export', 'standard'), true);
	assert.match(PAGE, /return canAccessSettingsTab\(preferred\) \? preferred : 'export';/);
});

// ------------------------------------------------------------------- T-51

test('T-51  narrowing the dialog moves off a tab that has just gone', () => {
	const setter = PAGE.slice(PAGE.indexOf('function setSettingsDetail'));
	const body = setter.slice(0, setter.indexOf('\n\t}'));
	assert.match(body, /settingsDetail = detail;/);
	// Through selectSettingsTab, so the tab it lands on loads what it needs --
	// assigning settingsTab here would show `export` with no templates fetched.
	assert.match(body, /if \(settingsOpen && !canAccessSettingsTab\(settingsTab\)\) selectSettingsTab\(defaultSettingsTab\(\)\)/);
});

// ------------------------------------------------------------------- T-52

test('T-52  the switch is in the dialog head and says which mode it is in', () => {
	assert.match(HEAD, /role="switch"/);
	assert.match(HEAD, /aria-checked=\{detailed\}/);
	assert.match(HEAD, /onSetSettingsDetail\(detailed \? 'standard' : 'detailed'\)/);
	assert.match(HEAD, /settingsDetailDetailed : t\(\)\.settingsDetailStandard/);
	// In the head next to the close button, not somewhere in a tab body.
	assert.match(HEAD, /class="modal-head-tools"/);
	// Model mode has four tabs of its own and none is detail-gated, so the
	// switch would govern nothing there.
	assert.match(HEAD, /\{#if settingsMode !== 'model'\}/);
});

test('T-52  the remembered mode is read through the normaliser', () => {
	assert.equal(normalizeSettingsDetail('detailed'), 'detailed');
	// Anything else opens the dialog narrow rather than throwing: a cleared
	// entry reads as null, and a corrupted one as a word nobody wrote.
	assert.equal(normalizeSettingsDetail('standard'), 'standard');
	assert.equal(normalizeSettingsDetail(null), 'standard');
	assert.equal(normalizeSettingsDetail('full'), 'standard');
	assert.equal(normalizeSettingsDetail(undefined), 'standard');
	assert.match(PAGE, /normalizeSettingsDetail\(localStorage\.getItem\(SETTINGS_DETAIL_KEY\)\)/);
	assert.match(PAGE, /localStorage\.setItem\(SETTINGS_DETAIL_KEY, detail\)/);
});
