// Run with: npm run test:unit  (node:test, no DOM dependency)
//
// SvelteKit server modules are shared by requests. The application keeps UI
// settings in module-scoped rune state, so the route must remain client-only.
// The inventory makes a new rune-state module visible in review instead of
// silently widening the reason for this boundary.
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

const ROUTES_DIR = dirname(fileURLToPath(import.meta.url));
const LIB_DIR = join(ROUTES_DIR, '..', 'lib');

function runeStateFiles(directory: string): string[] {
	return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
		const path = join(directory, entry.name);
		if (entry.isDirectory()) return runeStateFiles(path);
		if (!entry.name.endsWith('.svelte.ts')) return [];
		return readFileSync(path, 'utf8').includes('$state') ? [relative(LIB_DIR, path)] : [];
	});
}

test('the browser owns every module-scoped reactive setting', () => {
	const layout = readFileSync(join(ROUTES_DIR, '+layout.ts'), 'utf8');
	assert.match(layout, /^export const ssr = false;$/m);

	const instanceScoped = ['elapsed.svelte.ts', 'historyManagerState.svelte.ts'];
	const moduleScoped = [
		'features/batch/failure-report.svelte.ts',
		'features/batch/settings.svelte.ts',
		'features/color-catalog/settings.svelte.ts',
		'features/describe-panel/settings.svelte.ts',
		'features/export/download-folder.svelte.ts',
		'features/export/settings.svelte.ts',
		'features/model-inspection/state.svelte.ts',
		'features/result-log/settings.svelte.ts',
		'features/wild/settings.svelte.ts',
		'i18n/index.svelte.ts',
		'mascot.svelte.ts'
	];
	const allRuneState = runeStateFiles(LIB_DIR).sort();

	assert.deepEqual(allRuneState.filter((path) => !instanceScoped.includes(path)), moduleScoped);
	assert.deepEqual(allRuneState, [...instanceScoped, ...moduleScoped].sort());
});
