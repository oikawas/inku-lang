import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { test } from 'node:test';

const libRoot = new URL('../../', import.meta.url);
registerHooks({ resolve(specifier, context, nextResolve) {
	if (specifier.startsWith('$lib/')) {
		const file = new URL(`${specifier.slice(5)}.ts`, libRoot);
		return nextResolve((existsSync(file) ? file : new URL(`${specifier.slice(5)}/index.ts`, libRoot)).href, context);
	}
	return nextResolve(specifier, context);
} });
const identity = <T>(value: T): T => value;
(globalThis as unknown as Record<string, unknown>).$state = Object.assign(identity, { raw: identity });
(globalThis as unknown as Record<string, unknown>).$derived = Object.assign(identity, { by: <T>(read: () => T) => read() });
const { SessionState } = await import('./state.svelte.ts');

test('an older settings answer cannot overwrite a newer one', async () => {
	const pending: Array<(response: Response) => void> = [];
	const session = new SessionState({
		apiFetch: () => new Promise((resolve) => pending.push(resolve)),
		describeApiError: () => 'error', applyModelSettings: () => {}, afterAuthenticated: async () => {},
		afterSignedOut: () => {}, refreshUserAdministration: async () => {}, onVisibilityChanged: () => {}
	});
	const actor = { id: 'u', username: 'u', email: 'u@example.test', permission_groups: [], permission_group_labels: [],
		group_id: null, group_name: null, image_generation_count: 0, at: 1, ui_theme: 'dark' as const, tooltips_enabled: true };
	session.currentUser = actor;
	const theme = session.updateUiTheme(false);
	const tooltip = session.updateTooltipsEnabled(false);
	assert.equal(session.themeSaving, true);
	assert.equal(session.tooltipsSaving, true);
	pending[1](Response.json({ ...actor, ui_theme: 'light', tooltips_enabled: false }));
	await tooltip;
	pending[0](Response.json({ ...actor, ui_theme: 'light', tooltips_enabled: true }));
	await theme;
	assert.equal(session.currentUser?.tooltips_enabled, false);
	assert.equal(session.currentUser?.ui_theme, 'light');
	assert.equal(session.themeSaving, false);
	assert.equal(session.tooltipsSaving, false);
});
