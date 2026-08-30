// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

import { en } from './i18n/en.ts';
import { ja } from './i18n/ja.ts';

const here = path.dirname(new URL(import.meta.url).pathname);
const read = (relative: string) => fs.readFileSync(path.join(here, relative), 'utf8');
const PAGE = read('../routes/+page.svelte');
const PANEL = read('./components/CanvasPanel.svelte');
const ARTWORK = read('./features/canvas/CanvasArtworkWorkspace.svelte');
const HISTORY = read('./components/HistoryStrip.svelte');
const INPUT = read('./components/InputPanel.svelte');

test('the canvas header omits its scope badge and provider names', () => {
	assert.doesNotMatch(PANEL, /class="render-meta-scope"/);
	assert.match(PANEL, /statusStage1ModelOnly/);
	assert.match(PANEL, /statusStage2ModelOnly/);
	assert.match(PAGE, /modelShortName\(work\.displayedHistoryItem\.stage1_model\)/);
});

test('the canvas creation time explicitly stops at minutes', () => {
	const dateBlock = PAGE.slice(PAGE.indexOf('const currentRenderedAt'), PAGE.indexOf('/** One work older.'));
	assert.match(dateBlock, /minute: '2-digit'/);
	assert.doesNotMatch(dateBlock, /second:/);
});

test('the caption is left aligned and both fallbacks use explanatory tooltips', () => {
	assert.match(ARTWORK, /\.instruction-caption \{[\s\S]*?text-align: left;/);
	assert.match(ARTWORK, /<Tooltip placement="bottom-left" text=\{t\(\)\.interpretFallbackHint\(interpretFallbackReason\)\} wide>/);
	assert.match(ARTWORK, /<Tooltip placement="bottom-left" text=\{t\(\)\.composeFallbackHint\(composeFallbackDrawnReason\)\} wide>/);
	assert.doesNotMatch(ARTWORK, /title=\{t\(\)\.interpretFallbackHint/);
});

test('the three history filters follow the history button with one-em spacing', () => {
	const head = HISTORY.slice(HISTORY.indexOf('<div class="history-head">'), HISTORY.indexOf('{#if starredFilterClearedNotice}'));
	assert.ok(head.indexOf('history-title-btn') < head.indexOf('history-filter-group'));
	assert.ok(head.indexOf('history-filter-group') < head.indexOf('history-page-nav'));
	assert.match(HISTORY, /\.history-filter-group \{[^}]*margin-left: 1em;/);
});

test('the comment hint shares the row below the input with the character meter', () => {
	assert.match(INPUT, /<div class="input-meta-row">[\s\S]*inputCommentHint[\s\S]*input-meter[\s\S]*<\/div>/);
	assert.equal(ja.inputCommentHint, '[括弧内文字列はコメント扱い]');
	assert.equal(en.inputCommentHint, '[Text in brackets is treated as a comment]');
});
