// T-341 keeps every built-in colour word on its own preview rather than the generic fallback.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const PAGE = readFileSync(new URL('../routes/+page.svelte', import.meta.url), 'utf8');
const tableStart = PAGE.indexOf('const previews: Record<string, PreviewEntry> = {');
const tableEnd = PAGE.indexOf('\n\t\t};', tableStart);

assert.ok(tableStart >= 0 && tableEnd > tableStart, 'the built-in preview table must be present');
const PREVIEWS = PAGE.slice(tableStart, tableEnd);

test('T-341  yellow, orange, and purple have built-in bilingual preview drawings', () => {
	for (const word of ['黄', '橙', '紫']) {
		const entry = PREVIEWS.match(new RegExp(`^\\t\\t\\t${word}: \\{([^\\n]+)\\},$`, 'm'))?.[1];
		assert.ok(entry, `${word} must have a dedicated built-in preview entry`);
		for (const field of ['effect', 'example', 'effectEn', 'exampleEn']) {
			assert.match(entry, new RegExp(`${field}: ['\\"][^'\\"]+['\\"]`), `${word} must have a non-empty ${field}`);
		}
		assert.match(entry, /svg: (?:shapeSvg|lineSvg|scatter)/, `${word} must have a closed preview SVG`);
	}
});
