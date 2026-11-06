import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { annotate, highlightDDL, interpretationFeedback } from './highlight.ts';
import { resolveInstructionLang } from './instructionLang.ts';
import { ddlTitleName, ddlTitleLineSpans, withoutDdlTitleLines } from './ddl-titles.ts';

// A title line (DDL 27) names the chunk below it and draws nothing.
const DDL = '画面比1:1。\n\n「黒い水面」\n画面の横0.5、縦0.5の位置に、青の塗りの円を1個置く。';

test('title names, UTF-16 spans and body match the shared core cases', () => {
	const fixture = JSON.parse(readFileSync(new URL('../../../server/tests/data/ddl-title-cases.json', import.meta.url), 'utf8')) as {
		cases: Array<{ why: string; text: string; lines: Array<[number, number, string]>; without: string }>;
	};
	for (const { why, text, lines, without } of fixture.cases) {
		const scalars = Array.from(text);
		const utf16 = (offset: number) => scalars.slice(0, offset).join('').length;
		const expected = lines.map(([start, end, name]) => ({ start: utf16(start), end: utf16(end), name }));
		const actual = ddlTitleLineSpans(text).map(({ start, end }) => ({ start, end, name: ddlTitleName(text.slice(start, end)) }));
		assert.deepEqual(actual, expected, why);
		assert.equal(withoutDdlTitleLines(text), without, why);
	}
});

test('a title line is the core\'s: one bracketed name on a whole line', () => {
	assert.equal(ddlTitleName('「灯台」'), '灯台');
	assert.equal(ddlTitleName('　「 黒い水面 」 '), '黒い水面');
	assert.equal(ddlTitleName('"the “low” moon"'), 'the “low” moon');
	assert.equal(ddlTitleName('“lighthouse”'), 'lighthouse');
	assert.equal(ddlTitleName('「」'), '');
	for (const line of ['「赤い円」を中心に置く。', '「灯台」。', '「灯「台」', '"', '“lighthouse"', '画面比1:1。']) {
		assert.equal(ddlTitleName(line), null, line);
	}
	assert.equal(withoutDdlTitleLines('"灯台"\nplace one white circle at center.\n「」'), 'place one white circle at center.');
});

test('a DDL view shows a title line as a heading and colours no word in it', () => {
	const html = highlightDDL(DDL);
	assert.ok(html.includes('<span class="ddl-title">「黒い水面」</span>'), html);
	assert.ok(html.includes('ddl-token-color">青</span>'), html);
	assert.ok(!html.includes('ddl-token-color">黒</span>'), html);
	// A description's quoted line stays ordinary text.
	assert.ok(annotate('「黒い水面」').some((part) => part.kind === 'saijiki' && part.text === '黒'));
});

test('the language and the read words leave the titles out', () => {
	assert.equal(resolveInstructionLang('"灯台"\nplace one white circle at center.', 'ja'), 'en');
	assert.equal(resolveInstructionLang('"lighthouse"\n中心に白い円を置く。', 'en'), 'ja');
	const black = interpretationFeedback('黒い水面', DDL).find((part) => part.text === '黒');
	assert.equal(black?.tone, 'medium');
});
