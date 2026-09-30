import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

// LineagePanel drew its own image only for Nearby works, removed on
// 2026-09-22; its cards go through HistoryThumbnail. The model change dialog
// drew its own results until 2026-09-30; its options go through
// RefinementCandidateGrid. Both stay listed at zero so the {@html} check below
// still reads them.
const CONSUMERS: Record<string, number> = {
	'components/HistoryThumbnail.svelte': 1,
	'components/LineagePanel.svelte': 0,
	'components/ReplayComparisonModal.svelte': 2,
	'features/canvas/RefinementCandidateGrid.svelte': 1,
	'features/canvas/RefinementModelCompareView.svelte': 0
};

test('API-derived artwork SVG is loaded as an image document instead of app DOM', () => {
	for (const [file, expectedImages] of Object.entries(CONSUMERS)) {
		const source = readFileSync(fileURLToPath(new URL(`./${file}`, import.meta.url)), 'utf8');
		const imageActions = source.match(/use:svgImage=/g)?.length ?? 0;
		assert.equal(imageActions, expectedImages, `${file} must isolate each artwork in an image document`);
		assert.doesNotMatch(source, /\{@html\s+[^}]*[Ss]vg[^}]*\}/, `${file} must not inject artwork SVG into the app DOM`);
	}
});
