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

test('the timeline description keeps its complete Unicode text while removing only a batch prefix', () => {
	const description = '一二三四五六七八九十一二三四五六七八九十一';
	assert.equal(historyListDescription(`#12  ${description}`), description);
	assert.equal(historyListDescription('abcdefghijklmnopqrstu'), 'abcdefghijklmnopqrstu');
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

test('list, thumbnail and preview `#` buttons copy the work UUID with the canvas copy feedback', () => {
	assert.doesNotMatch(MANAGER, /function hashLabel/);
	assert.match(MANAGER, /const id = item\.id;/);
	assert.doesNotMatch(MANAGER, /function copyHash/);
	assert.doesNotMatch(MANAGER, /render_hash \|\|/);
	assert.equal(MANAGER.match(/aria-label=\{t\(\)\.historyIdCopyTitle\}>#<\/button>/g)?.length, 2);
	assert.match(MANAGER, /copiedHistoryId === it\.id \? t\(\)\.historyHashCopied : t\(\)\.historyIdCopyTitle/g);
	// The preview names the work by the UUID's first eight characters, the
	// value the copy button puts on the clipboard, not by the rh3 suffix.
	assert.match(MANAGER, /<dt>\{t\(\)\.historyIdHeader\}<\/dt>/);
	assert.match(MANAGER, /\{previewItem\.id\.slice\(0, 8\)\}/);
	assert.doesNotMatch(MANAGER, /previewItem\.render_hash\.slice\(-4\)/);
	assert.match(MANAGER, /\}, 1200\);/);
	for (const pack of [JA, EN]) {
		assert.match(pack, /historyHashCopied:/);
		assert.match(pack, /historyIdCopyTitle: .*UUID/);
		assert.match(pack, /historyIdHeader: 'ID'/);
	}
	assert.match(TYPES, /historyHashCopied: string;/);
	assert.match(TYPES, /historyIdCopyTitle: string;/);
});

test('the canvas `#` button copies the saved work UUID, and hides for an unsaved preview', () => {
	const WORKSPACE = read('../features/canvas/CanvasArtworkWorkspace.svelte');
	assert.match(WORKSPACE, /const copyableWorkId = \$derived\(unsavedRefinementPreview \? null : currentHistoryId\);/);
	assert.match(WORKSPACE, /\{#if copyableWorkId\}/);
	assert.match(WORKSPACE, /await onCopyWorkId\(value\);/);
	assert.doesNotMatch(WORKSPACE, /onCopyStatusHash|full hash/);
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
