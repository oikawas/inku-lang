// Run with: npm run test:unit  (node:test, no test dependency)
//
// With the setting on, choosing another work from the history strip while the
// generation-information drawer is open keeps the drawer open; the drawer then
// shows the chosen work. The setting is per account, on by default.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import {
	FOLLOW_DEFAULT,
	FOLLOW_FIELD,
	followFromSettings,
	pressChoosesWork,
	SELECTS_WORK_ATTRIBUTE
} from './generation-info-follow.ts';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');

test('an account that never chose follows the strip', () => {
	assert.equal(FOLLOW_DEFAULT, true);
	assert.equal(followFromSettings(null), true);
	assert.equal(followFromSettings({}), true);
	assert.equal(followFromSettings({ sketch_open: false }), true);
});

test('a stored choice is read back, and nothing else is taken for one', () => {
	assert.equal(followFromSettings({ [FOLLOW_FIELD]: false }), false);
	assert.equal(followFromSettings({ [FOLLOW_FIELD]: true }), true);
	assert.equal(followFromSettings({ [FOLLOW_FIELD]: 'false' }), FOLLOW_DEFAULT);
});

// A stand-in for an element: which selectors its ancestors (itself included) match.
const pressed = (...matches: string[]) => ({
	closest: (selector: string) => (matches.includes(selector) ? {} : null)
});
const WORK = `[${SELECTS_WORK_ATTRIBUTE}]`;

test('a press on a history-strip work chooses it', () => {
	assert.equal(pressChoosesWork(pressed(WORK)), true);
});

test('the star inside a work does not choose it, nor does a press elsewhere', () => {
	assert.equal(pressChoosesWork(pressed(WORK, 'button')), false);
	assert.equal(pressChoosesWork(pressed('button')), false);
	assert.equal(pressChoosesWork(pressed()), false);
	assert.equal(pressChoosesWork(null), false);
});

test('a lineage selection button and its contents choose the work; its other controls do not', () => {
	const cardButton = {};
	const cardContent = { closest: (selector: string) => selector === WORK || selector === 'button' ? cardButton : null };
	assert.equal(pressChoosesWork(cardContent), true);
	for (const control of ['star', 'revision', 'menu', 'checkbox', 'branch', 'details']) {
		const otherControl = { closest: (selector: string) => selector === 'button' && control !== 'checkbox' ? {} : null };
		assert.equal(pressChoosesWork(otherControl), false, control);
	}
	const lineage = read('../../components/LineagePanel.svelte');
	assert.match(lineage, /class="card-main" data-selects-work=\{node\.history \? '' : undefined\}/);
});

test('each history-strip work carries the attribute the drawer looks for', () => {
	const strip = read('../../components/HistoryStrip.svelte');
	const thumb = strip.slice(strip.indexOf('class="thumb"'), strip.indexOf('onclick={() => !interactionLocked && onLoadItem(it)}'));
	assert.ok(thumb.includes(SELECTS_WORK_ATTRIBUTE), 'the .thumb element must carry data-selects-work');
});

test('the drawer closes on a press outside unless the setting keeps it for a chosen work', () => {
	const panel = read('../../components/CanvasPanel.svelte');
	assert.match(panel, /generationInfoSettings\.followsSelection && target instanceof Element && pressChoosesWork\(target\)\) return;\s*closeGenerationInfo\(\);/);
});

test('lineage has the shared drawer toggle at the work-tab position and tab changes keep it open', () => {
	const panel = read('../../components/CanvasPanel.svelte');
	assert.match(panel, /onpointerdowncapture=/);
	assert.match(panel, /lineageGenerationInfoToggleEl\?\.contains\(target\)/);
	assert.match(panel, /target\.closest\('\[data-generation-info-tab\]'\)/);
	assert.match(panel, /onToggleGenerationInfo=\{toggleGenerationInfo\}/);
	assert.match(panel, /outputTab === 'lineage'[\s\S]*?bind:this=\{lineageGenerationInfoToggleEl\}[\s\S]*?onclick=\{toggleGenerationInfo\}/);
	assert.match(panel, /lineage-generation-info-control \{ position: absolute; right: 178px; bottom: 14px;/);
});
