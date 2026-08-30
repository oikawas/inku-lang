import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const CONSUMERS: Record<string, number> = {
	'components/HistoryThumbnail.svelte': 1,
	'components/LineagePanel.svelte': 1,
	'components/ReplayComparisonModal.svelte': 2,
	'features/canvas/RefinementAdjustView.svelte': 1,
	'features/canvas/RefinementModelCompareView.svelte': 2
};

test('API-derived artwork SVG is loaded as an image document instead of app DOM', () => {
	for (const [file, expectedImages] of Object.entries(CONSUMERS)) {
		const source = readFileSync(fileURLToPath(new URL(`./${file}`, import.meta.url)), 'utf8');
		const imageActions = source.match(/use:svgImage=/g)?.length ?? 0;
		assert.equal(imageActions, expectedImages, `${file} must isolate each artwork in an image document`);
		assert.doesNotMatch(source, /\{@html\s+[^}]*[Ss]vg[^}]*\}/, `${file} must not inject artwork SVG into the app DOM`);
	}
});
