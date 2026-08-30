import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

for (const component of ['AIRefineModal.svelte', 'ManualRefineModal.svelte']) {
	test(`${component} closes only for a click on its own backdrop`, () => {
		const source = readFileSync(fileURLToPath(new URL(`./${component}`, import.meta.url)), 'utf8');
		assert.match(source, /function handleBackdropClick\(event: MouseEvent\)/);
		assert.match(source, /event\.target === event\.currentTarget/);
		assert.match(source, /class="modal-backdrop" onclick=\{handleBackdropClick\}/);
		assert.doesNotMatch(source, /stopPropagation\(\)/);
	});
}
