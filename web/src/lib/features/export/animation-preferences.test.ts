import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { compileModule } from 'svelte/compiler';
import ts from 'typescript';

test('animation defaults and last-used settings follow the signed-in user', async () => {
	const identity = <T>(value: T): T => value;
	const state = identity as (<T>(value: T) => T) & { raw: <T>(value: T) => T };
	state.raw = identity;
	(globalThis as unknown as Record<string, unknown>).$state = state;
	const previous = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
	const entries = new Map<string, string>();
	Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
		getItem: (key: string) => entries.get(key) ?? null,
		setItem: (key: string, value: string) => entries.set(key, value),
	} });
	try {
		const stub = (source: string) => JSON.stringify('data:text/javascript,' + encodeURIComponent(source));
		const source = readFileSync(new URL('./settings.svelte.ts', import.meta.url), 'utf8')
			.replace("'$lib/animationExport'", JSON.stringify(new URL('../../animationExport.ts', import.meta.url).href))
			.replace("'$lib/cardExport'", stub('export const DEFAULT_CARD_EXPORT_SETTINGS = {}; export const parseCardExportSettings = () => ({});'))
			.replace("'$lib/clipboardExport'", stub('export const DEFAULT_CLIPBOARD_EXPORT_SETTINGS = {}; export const parseClipboardExportSettings = () => ({});'))
			.replace("'$lib/features/persisted-settings'", stub('export const registerPersistedSetting = () => {};'));
		const javascript = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.ESNext } }).outputText;
		const compiled = compileModule(javascript, { filename: 'export-settings.svelte.js', generate: 'client' }).js.code
			.replace(/(['"])svelte\/internal\/client\1/g, JSON.stringify(import.meta.resolve('svelte/internal/client')));
		const { exportSettings: settings } = await import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64'));
		settings.setAnimationOwner('alice');
		settings.rememberAnimation('alice', { ...settings.selectedAnimation, format: 'gif', showDdl: false });
		settings.setAnimationOwner('bob');
		assert.equal(settings.selectedAnimation.format, 'apng');
		settings.selectedAnimation = { ...settings.selectedAnimation, pattern: 'slide' };
		settings.setAnimationOwner(null);
		settings.setAnimationOwner('alice');
		assert.equal(settings.selectedAnimation.format, 'gif');
		assert.equal(settings.selectedAnimation.showDdl, false);
		settings.setAnimationOwner('bob');
		assert.equal(settings.selectedAnimation.format, 'apng');
		assert.equal(settings.selectedAnimation.pattern, 'slide');
	} finally {
		if (previous) Object.defineProperty(globalThis, 'localStorage', previous);
		else Reflect.deleteProperty(globalThis, 'localStorage');
	}
});
