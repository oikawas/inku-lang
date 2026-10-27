import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { compileModule } from 'svelte/compiler';
import ts from 'typescript';

test('the next drawing switch is separate from the saved default', async () => {
	const contents = new Map<string, string>([['inku-wild', '1']]);
	const previous = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
	Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
		getItem: (key: string) => contents.get(key) ?? null,
		setItem: (key: string, value: string) => contents.set(key, value),
	} });
	try {
		const source = readFileSync(new URL('./settings.svelte.ts', import.meta.url), 'utf8')
			.replace("'$lib/features/wild/render'", JSON.stringify(new URL('./render.ts', import.meta.url).href))
			.replace("'$lib/features/persisted-settings'", JSON.stringify(new URL('../persisted-settings.ts', import.meta.url).href));
		const javascript = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.ESNext } }).outputText;
		const compiled = compileModule(javascript, { filename: 'wild-settings.svelte.js', generate: 'client' }).js.code
			.replace(/(['"])svelte\/internal\/client\1/g, JSON.stringify(import.meta.resolve('svelte/internal/client')));
		const { wildSettings } = await import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64'));
		wildSettings.load();
		assert.equal(wildSettings.enabled, false, 'the old per-drawing selection is not a saved default');
		assert.equal(wildSettings.selected, false);
		wildSettings.set(true);
		assert.equal(contents.get('inku-wild-default'), '1');
		assert.equal(wildSettings.selected, true);
		wildSettings.setSelected(false);
		assert.equal(wildSettings.enabled, true);
		assert.equal(contents.get('inku-wild-default'), '1');
		wildSettings.load();
		assert.equal(wildSettings.selected, true, 'a later start takes the saved default');
		wildSettings.set(false);
		assert.equal(contents.get('inku-wild-default'), '0');
		assert.equal(wildSettings.selected, false);
	} finally {
		if (previous) Object.defineProperty(globalThis, 'localStorage', previous);
		else Reflect.deleteProperty(globalThis, 'localStorage');
	}
});
