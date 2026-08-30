// Run with: node --import ./scripts/ts-extensionless-resolve.mjs --test src/lib/components/history-manager-interactive-polish.test.ts
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { formatHistoryMinute, historyListDescription } from '../historyManagerPresentation.ts';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const MANAGER = read('./HistoryManager.svelte');
const STATE = read('../historyManagerState.svelte.ts');
const JA = read('../i18n/ja.ts');
const EN = read('../i18n/en.ts');
const TYPES = read('../i18n/types.ts');

test('the timeline description is the first twenty Unicode characters', () => {
	assert.equal(historyListDescription('#12  一二三四五六七八九十一二三四五六七八九十一'), '一二三四五六七八九十一二三四五六七八九十');
	assert.equal(Array.from(historyListDescription('abcdefghijklmnopqrstu')).length, 20);
});

test('the timeline creation date stops at minutes', () => {
	const value = formatHistoryMinute(new Date('2026-08-30T12:34:56Z').getTime(), 'en-US', 'UTC');
	assert.match(value, /12:34/);
	assert.doesNotMatch(value, /:56/);
});

test('the timeline columns show description and SVG size, but no elapsed seconds', () => {
	const head = MANAGER.slice(MANAGER.indexOf('<table class="history-table">'), MANAGER.indexOf('<tbody>'));
	assert.ok(head.indexOf('historyDescriptionHeader') < head.indexOf('historyModelHeader'));
	assert.match(head, /historySvgSizeHeader/);
	assert.doesNotMatch(head, /historySecondsHeader/);
	assert.match(MANAGER, /historyListDescription\(it\.source_text \?\? it\.input\)/);
	assert.match(MANAGER, /formatHistoryMinute\(it\.at,/);
	assert.match(MANAGER, /formatByteSize\(it\.svg_bytes\)/);
	assert.doesNotMatch(MANAGER, /formatElapsed\(it\.elapsed_ms\)/);
	for (const pack of [JA, EN]) {
		assert.match(pack, /historyDescriptionHeader:/);
		assert.match(pack, /historySvgSizeHeader:/);
	}
	assert.match(TYPES, /historyDescriptionHeader: string;/);
	assert.match(TYPES, /historySvgSizeHeader: string;/);
	assert.match(STATE, /svg_bytes\?: number;/);
});

test('the timeline revision control belongs to the actions column, not the thumbnail cell', () => {
	const thumbCell = MANAGER.slice(MANAGER.indexOf('<td class="table-thumb-cell">'), MANAGER.indexOf('</td>', MANAGER.indexOf('<td class="table-thumb-cell">')));
	assert.doesNotMatch(thumbCell, /onToggleForRevision/);
	const actionCellAt = MANAGER.indexOf('<td class="table-actions">');
	assert.ok(actionCellAt >= 0);
	const actionCell = MANAGER.slice(actionCellAt, MANAGER.indexOf('</td>', actionCellAt));
	assert.match(actionCell, /onToggleForRevision\(it, event\)/);
});

test('list and thumbnail hash buttons match the canvas full-hash copy feedback', () => {
	assert.doesNotMatch(MANAGER, /function hashLabel/);
	assert.match(MANAGER, /const hash = item\.render_hash;/);
	assert.doesNotMatch(MANAGER, /render_hash \|\|/);
	assert.equal(MANAGER.match(/aria-label=\{t\(\)\.historyHashCopyTitle\}>#<\/button>/g)?.length, 2);
	assert.match(MANAGER, /copiedHistoryHash === it\.render_hash \? t\(\)\.historyHashCopied : t\(\)\.historyHashCopyTitle/g);
	assert.match(MANAGER, /\}, 1200\);/);
	for (const pack of [JA, EN]) assert.match(pack, /historyHashCopied:/);
	assert.match(TYPES, /historyHashCopied: string;/);
});

test('lineage thumbnails form a parent-first horizontal generation lane', () => {
	assert.match(MANAGER, /function lineageLaneItems\(group: LineageHistoryGroup\)/);
	assert.match(MANAGER, /item\.lineage_node_id === group\.root_node_id/);
	assert.match(MANAGER, /\{#if !lineageThumbsMode\}\s*<button class="lineage-representative"/);
	assert.match(MANAGER, /\{#if lineageThumbsMode \|\| expandedRootIds\.includes\(group\.root_node_id\)\}/);
	assert.match(MANAGER, /lineageThumbsMode \? lineageLaneItems\(group\) : membersInGenerationOrder/);
	assert.match(MANAGER, /\.lineage-history-list\.thumbs-mode \.lineage-member-grid \{[^}]*display: flex;[^}]*overflow-x: auto;/s);
	assert.match(MANAGER, /\.lineage-history-list\.thumbs-mode \.lineage-member \{[^}]*flex: 0 0 142px;[^}]*scroll-snap-align: start;/);
	assert.doesNotMatch(MANAGER, /thumbs-mode \.lineage-member-grid \{ grid-template-columns: 1fr; \}/);
});
