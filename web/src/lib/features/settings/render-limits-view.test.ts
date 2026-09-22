// Run with the focused Stage 3C command in the contract.
//
// This source-level seam keeps render-limit presentation, vocabulary, and
// sizing rationale beside the Settings feature while the route-instance
// controller remains the only state and operation owner.
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const VIEW_URL = new URL('./RenderLimitsSettings.svelte', import.meta.url);
const VIEW = existsSync(VIEW_URL) ? read('./RenderLimitsSettings.svelte') : '';
const OWNER = read('./server-administration.svelte.ts');
const MODAL = read('../../components/SettingsModal.svelte');
const LIMITS_BRANCH = MODAL.slice(
	MODAL.indexOf("{:else if settingsTab === 'limits'}"),
	MODAL.indexOf("{:else if settingsTab === 'plugins'}")
);

test('Stage 3C gives render-limit presentation one feature-local view', () => {
	assert.notEqual(VIEW, '', 'RenderLimitsSettings.svelte');
	assert.match(MODAL, /import RenderLimitsSettings from '\$lib\/features\/settings\/RenderLimitsSettings\.svelte'/);
	assert.match(LIMITS_BRANCH, /<RenderLimitsSettings/);
	assert.doesNotMatch(LIMITS_BRANCH, /settingsRenderLimitsTitle|limits-group|markWeight/);
	for (const helper of ['renderLimitLabel', 'renderLimitHint', 'renderLimitGroupLabel', 'renderLimitGroupTooltip']) {
		assert.match(VIEW, new RegExp('function ' + helper + '\\b'), helper);
		assert.doesNotMatch(MODAL, new RegExp('function ' + helper + '\\b'), helper);
	}
	assert.match(VIEW, /import \{ markWeight \} from '\$lib\/markWeight'/);
	assert.doesNotMatch(MODAL, /import \{ markWeight \} from '\$lib\/markWeight'/);
});

test('the focused view receives one render-limits slice and named capabilities', () => {
	assert.match(VIEW, /type RenderLimitsStatus = SettingsStatus\['render_limits'\];/);
	assert.match(VIEW, /status: RenderLimitsStatus \| null;/);
	assert.doesNotMatch(VIEW, /SettingsController|apiFetch|\/api\//);
	assert.match(LIMITS_BRANCH, /status=\{settingsStatus\?\.render_limits \?\? null\}/);
	for (const capability of ['onReload', 'onUpdate']) {
		assert.match(VIEW, new RegExp(capability + ':'), capability);
		assert.match(LIMITS_BRANCH, new RegExp(capability + '='), capability);
	}
	for (const owner of ['loadSettingsStatus', 'updateRenderLimits']) {
		assert.match(OWNER, new RegExp('async function ' + owner + '\\('), owner);
		assert.doesNotMatch(VIEW, new RegExp('(?:async\\s+)?function ' + owner + '\\('), owner);
	}
});
