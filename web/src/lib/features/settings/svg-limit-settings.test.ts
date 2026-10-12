import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { transpileModule, ModuleKind } from 'typescript';

// Exercise the view's operations without a browser. Derived expressions remain
// getters so edits are observed at the same boundaries as Svelte reactivity.
function panel(status: Record<string, unknown>, update: (patch: Record<string, number>) => Promise<unknown>) {
	const source = readFileSync(new URL('./RenderLimitsSettings.svelte', import.meta.url), 'utf8');
	let script = source.split('<script lang="ts">')[1].split('</script>')[0]
		.replace(/^\s*import .*;\s*$/gm, '')
		.replace(/const changedFields = \$derived\(([\s\S]*?)\n\t\);/, 'function getChangedFields() { return ($1); }')
		.replace(/const hasChanges = \$derived\((.*?)\);/, 'function getHasChanges() { return $1; }')
		.replace(/\bchangedFields\b/g, 'getChangedFields()')
		.replace(/\bhasChanges\b/g, 'getHasChanges()');
	script += `
	return { renderLimitBounds, restoreDefaults, discardChanges, saveChanges,
		edit: (field, value) => { draft = { ...draft, [field]: value }; },
		draft: () => draft, changed: () => getChangedFields() };
	`;
	const compiled = transpileModule(script, { compilerOptions: { module: ModuleKind.None } }).outputText;
	const effects: (() => void)[] = [];
	const result = new Function('$props', '$state', '$effect', compiled)(
		() => ({ status, isAdmin: true, onUpdate: update }),
		(value: unknown) => value,
		(effect: () => void) => effects.push(effect),
	);
	effects.forEach((effect) => effect());
	return result;
}

test('SVG uses dedicated bounds and joins partial save, cancel, and defaults', async () => {
	const status = {
		limits: { max_generated_svg_mib: 7, max_instructions: 200 },
		defaults: { max_generated_svg_mib: 12, max_instructions: 256 },
		absolute_max: 100000,
		field_bounds: { max_generated_svg_mib: { min: 1, max: 32, step: 1 } },
	};
	const patches: Record<string, number>[] = [];
	const view = panel(status, async (patch) => {
		patches.push(patch);
		return { ...status, limits: { ...status.limits, ...patch } };
	});
	assert.deepEqual(view.renderLimitBounds('max_generated_svg_mib'), { min: 1, max: 32, step: 1 });
	assert.deepEqual(view.renderLimitBounds('max_instructions'), { min: 1, max: 100000, step: 1 });
	view.edit('max_generated_svg_mib', 32);
	view.discardChanges();
	assert.equal(view.draft().max_generated_svg_mib, 7);
	assert.deepEqual(view.changed(), []);
	view.edit('max_generated_svg_mib', 1);
	await view.saveChanges();
	assert.deepEqual(patches, [{ max_generated_svg_mib: 1 }]);
	assert.deepEqual(view.changed(), []);
	view.restoreDefaults();
	assert.deepEqual(view.draft(), status.defaults);
	assert.equal(patches.length, 1, 'defaults remain a draft until Save changes');
	await view.saveChanges();
	assert.deepEqual(patches[1], status.defaults);
});
