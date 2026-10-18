// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

const here = path.dirname(new URL(import.meta.url).pathname);
const MANAGER = fs.readFileSync(path.join(here, 'components/HistoryManager.svelte'), 'utf8');
const STRIP = fs.readFileSync(path.join(here, 'components/HistoryStrip.svelte'), 'utf8');

function rule(source: string, selector: string): Record<string, string> {
	const start = source.indexOf(`${selector} {`);
	assert.ok(start >= 0, `no rule for ${selector}`);
	assert.equal(source.indexOf(`${selector} {`, start + 1), -1, `two rules for ${selector}`);
	const body = source.slice(source.indexOf('{', start) + 1, source.indexOf('}', start));
	return Object.fromEntries(
		body.split(';').map((d) => d.trim()).filter(Boolean).map((d) => {
			const [k, ...v] = d.split(':');
			return [k.trim(), v.join(':').trim()];
		})
	);
}

test('a time-ordered Library card marks the work shown on the canvas', () => {
	assert.match(
		MANAGER,
		/<HistoryThumbnail item=\{it\} scope="manager" size="manager" \/>\s*\{#if it\.id && currentHistoryId === it\.id\}<span class="thumb-current-badge">\{t\(\)\.historyCurrentBadge\}<\/span>\{\/if\}/
	);
});

test('in a lineage lane the work shown takes the generation number badge place', () => {
	assert.match(
		MANAGER,
		/\{#if lineageThumbsMode && it\.id && currentHistoryId === it\.id\}<span class="lineage-current-badge">\{t\(\)\.historyCurrentBadge\}<\/span>\{:else if lineageThumbsMode && it\.lineage_generation != null\}<span class="lineage-generation-badge"/
	);
});

test('both Library badges look like the history strip badge', () => {
	const strip = rule(STRIP, '.thumb-current-badge');
	const look = ['background', 'color', 'font-size', 'padding', 'border-radius'];
	for (const selector of ['.manager-thumb .thumb-current-badge', '.lineage-current-badge']) {
		const own = rule(MANAGER, selector);
		for (const key of look) assert.equal(own[key], strip[key], `${selector} ${key}`);
	}
	const card = rule(MANAGER, '.manager-thumb .thumb-current-badge');
	assert.equal(card.bottom, strip.bottom);
	assert.equal(card.right, strip.right);
});
