import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { compile, compileModule } from 'svelte/compiler';
import { render } from 'svelte/server';
import ts from 'typescript';
import { editNumericRange, matchingRange, parseRangeBody, readCompositionRanges, scanNumericRanges, type RangePreview } from './composition-ranges.ts';
import { highlightDDL } from './highlight.ts';

// Two representative core-shaped rows suffice; production has no copied table.
const ranges = readCompositionRanges({ schema: 'inku.composition-ranges.v1', ranges: [
	{ key: 'left', words: { ja: '左上', en: 'top left' }, bounds: [[0, 1], [0, 1], [1, 3], [1, 3]], corner: false },
	{ key: 'right', words: { ja: '右下', en: 'bottom right' }, bounds: [[2, 3], [2, 3], [1, 1], [1, 1]], corner: false }
] });

test('only equal words and exact rationals fold; language-specific syntax stays bounded', () => {
	const fullwidth = scanNumericRanges('［構図］右下（横４／６～１，縦２／３~１）に、円。')[0];
	assert.equal(matchingRange(fullwidth, ranges)?.key, 'right');
	assert.equal(matchingRange(scanNumericRanges('左上（横2/3〜1、縦2/3〜1）に、円。')[0], ranges), undefined);
	assert.equal(matchingRange(scanNumericRanges('左上（横0〜0.333333、縦0〜1/3）に、円。')[0], ranges), undefined);
	const english = scanNumericRanges('A circle at [composition] the top left (horizontal 0 to 2/6, vertical 0 to 1/3).')[0];
	assert.equal(matchingRange(english, ranges)?.key, 'left');
	assert.equal(matchingRange(scanNumericRanges('A circle ON the top left (HORIZONTAL 0 TO 1/3, VERTICAL 0 TO 1/3).')[0], ranges)?.key, 'left');
	assert.equal(matchingRange(scanNumericRanges('A circle ON the Top Left (HORIZONTAL 0 TO 1/3, VERTICAL 0 TO 1/3).')[0], ranges), undefined);
	assert.equal(parseRangeBody('horizontal ０ to 1/3, vertical 0 to 1/3', 'en'), null);
	assert.equal(parseRangeBody('horizontal 0 ~ 1/3, vertical 0 to 1/3', 'en'), null);
	assert.equal(parseRangeBody('横0〜1/1000001、縦0〜1', 'ja'), null);
	for (const digit of ['⓪', '⁰']) assert.equal(parseRangeBody(`横${digit}〜1/3、縦0〜1/3`, 'ja'), null);
	assert.equal(parseRangeBody('横0〜1 / 3、縦0〜1/3', 'ja'), null);
	assert.equal(scanNumericRanges('画面の横0.2〜0.5、縦0〜0.3の範囲に、円。').length, 0);
	assert.match(highlightDDL('上の3分の2（横0〜1、縦0〜2/3）に、円。'), /ddl-token-place">上の3分の2<\/span>/);
});

test('editing only the range follows matching names and preserves surrounding source bytes', () => {
	const source = '  紙。\n［構図］右下（横2/3〜1、縦2/3〜1）に、赤い円。\n青い線。  ';
	const range = scanNumericRanges(source)[0];
	const left = editNumericRange(source, range, '横０〜１／３、縦０〜１／３', ranges);
	assert.equal(left.source, '  紙。\n［構図］左上（横０〜１／３、縦０〜１／３）に、赤い円。\n青い線。  ');
	const custom = editNumericRange(left.source, left.range, '横0.1〜0.4、縦0.2〜0.5', ranges);
	assert.equal(custom.range.name, '指定の範囲');
	assert.equal(matchingRange(custom.range, ranges), undefined);
	for (const body of ['横1〜0、縦0〜1', '横0〜1.1、縦0〜1', '横0〜0、縦0〜1', 'typing']) {
		const invalid = editNumericRange(source, range, body, ranges);
		assert.equal(invalid.range.bounds, null);
		assert.ok(invalid.source.includes(`（${body}）`));
	}
	assert.deepEqual(readCompositionRanges({ schema: 'wrong', ranges: [] }), []);
	assert.deepEqual(readCompositionRanges({ schema: 'inku.composition-ranges.v1', ranges: [{ bounds: 'invalid' }] }), []);
});

test('Japanese hyphens accept the reported edit and follow the matching range name', () => {
	assert.deepEqual(parseRangeBody('横1/3-2/3、縦2/3〜1', 'ja'), [[1n, 3n], [2n, 3n], [2n, 3n], [1n, 1n]]);
	const source = '右下（横2/3〜1、縦2/3〜1）に、赤い円。';
	for (const body of ['横0-1/3、縦0－1/3', '横０ － １／３、縦０ - １／３']) {
		const edited = editNumericRange(source, scanNumericRanges(source)[0], body, ranges);
		assert.equal(edited.source, `左上（${body}）に、赤い円。`);
		assert.equal(matchingRange(scanNumericRanges(edited.source)[0], ranges)?.key, 'left');
	}
});

test('English hyphens and en dashes follow matching range names with optional spaces', () => {
	const source = 'A circle at the bottom right (horizontal 2/3 to 1, vertical 2/3 to 1).';
	for (const body of ['horizontal 0-1/3, vertical 0–1/3', 'horizontal 0 – 1/3, vertical 0 - 1/3']) {
		assert.deepEqual(parseRangeBody(body, 'en'), ranges[0].bounds);
		const edited = editNumericRange(source, scanNumericRanges(source)[0], body, ranges);
		assert.equal(edited.source, `A circle at the top left (${body}).`);
		assert.equal(matchingRange(scanNumericRanges(edited.source)[0], ranges)?.key, 'left');
	}
});

function dataModule(code: string): string { return 'data:text/javascript;base64,' + Buffer.from(code).toString('base64'); }
function runeModule(path: string, mode: 'client' | 'server'): string {
	const source = ts.transpileModule(readFileSync(new URL(path, import.meta.url), 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.ESNext } }).outputText;
	return dataModule(compileModule(source, { filename: path.replace(/\.ts$/, '.js'), generate: mode }).js.code
		.replace(/(['"])(svelte\/internal\/(?:client|server))\1/g, (_, _quote, name) => JSON.stringify(import.meta.resolve(name)))
		.replaceAll("'./composition-ranges'", JSON.stringify(new URL('./composition-ranges.ts', import.meta.url).href))
		.replaceAll("'./ja'", JSON.stringify(new URL('./i18n/ja.ts', import.meta.url).href))
		.replaceAll("'./en'", JSON.stringify(new URL('./i18n/en.ts', import.meta.url).href)));
}

test('range names return to the opened words or the chosen place when numbers leave the table', async () => {
	const { createRangeEditState } = await import(runeModule('./range-edit.svelte.ts', 'client'));
	for (const lang of ['ja', 'en'] as const) {
		const tableName = ranges[1].words[lang];
		const chosen = lang === 'ja' ? '指定の範囲' : 'chosen place';
		const customName = lang === 'ja' ? '月のあたり' : 'near the moon';
		const originalBody = lang === 'ja' ? '横2/3〜1、縦2/3〜1' : 'horizontal 2/3 to 1, vertical 2/3 to 1';
		const customBody = lang === 'ja' ? '横0〜0.5、縦0〜2/3' : 'horizontal 0 to 0.5, vertical 0 to 2/3';
		const tableBody = lang === 'ja' ? '横0〜1/3、縦0〜1/3' : 'horizontal 0 to 1/3, vertical 0 to 1/3';
		const text = (name: string, body: string) => lang === 'ja'
			? `［構図］${name}（${body}）に、赤い円。`
			: `A red circle at [composition] the ${name} (${body}).`;
		for (const openedName of [tableName, chosen, customName]) {
			let source = text(openedName, originalBody);
			const state = createRangeEditState({ source: () => source, ranges: () => ranges, disabled: () => false,
				change: (next: string) => source = next, preview() {}, invalid() {} });
			state.open(scanNumericRanges(source)[0]);
			assert.equal(source, text(openedName, originalBody), 'opening alone keeps saved words');
			state.edit(customBody);
			const expected = openedName === customName ? customName : chosen;
			assert.equal(source, text(expected, customBody));
			assert.equal(matchingRange(scanNumericRanges(source)[0], ranges), undefined);
			state.edit(tableBody);
			assert.equal(matchingRange(scanNumericRanges(source)[0], ranges)?.key, 'left');
			state.edit('typing');
			assert.equal(state.active.range.name, ranges[0].words[lang], 'invalid numbers keep the last words');
			state.edit(customBody);
			assert.equal(source, text(expected, customBody), 'passing through table numbers restores the opened custom words');
			state.edit(tableBody);
			assert.equal(source, text(ranges[0].words[lang], tableBody));
		}
	}
});

test('instance-scoped rune edits retain the last valid frame, honor locks, and clear on leaving', async () => {
	const { createRangeEditState } = await import(runeModule('./range-edit.svelte.ts', 'client'));
	let source = '右下（横2/3〜1、縦2/3〜1）に、円。';
	let preview: RangePreview | null = null;
	let invalid = false;
	let locked = false;
	const changes: string[] = [];
	const state = createRangeEditState({ source: () => source, ranges: () => ranges, disabled: () => locked,
		change: (next: string) => { changes.push(next); source = next; }, preview: (next: RangePreview | null) => preview = next, invalid: (next: boolean) => invalid = next });
	const other = createRangeEditState({ source: () => source, ranges: () => ranges, disabled: () => false, change() {}, preview() {}, invalid() {} });
	state.open(scanNumericRanges(source)[0]);
	state.edit('横0〜1/3、縦0〜1/3');
	const last = preview!.bounds;
	state.edit('not a range');
	assert.equal(changes.length, 2);
	assert.ok(source.includes('（not a range）'));
	assert.deepEqual(preview!.bounds, last);
	assert.equal(preview!.invalid, true);
	assert.equal(invalid, true);
	assert.equal(other.active, null);
	locked = true;
	state.edit('横0〜1、縦0〜1');
	assert.equal(changes.length, 2);
	state.reset();
	assert.equal(preview, null);
	assert.equal(invalid, true);
	locked = false;
	source += '\n右下（横2/3〜1、縦2/3〜1）に、青い円。';
	state.open(scanNumericRanges(source)[0]);
	state.edit('横0.1〜0.4、縦0.2〜0.5');
	assert.equal(invalid, true);
	state.reset(true);
	assert.equal(invalid, false);
	source = '左上（横0〜1/3、縦0〜1/3）に、円。';
	state.sync();
	assert.equal(invalid, false);
});

test('the actual viewer SSR folds only its display and retains the complete fallback source', async () => {
	const aliases: Record<string, string> = {
		'$lib/highlight': new URL('./highlight.ts', import.meta.url).href,
		'$lib/composition-ranges': new URL('./composition-ranges.ts', import.meta.url).href,
		'$lib/ddl-source': new URL('./ddl-source.ts', import.meta.url).href,
		'$lib/range-edit.svelte': runeModule('./range-edit.svelte.ts', 'server'),
		'$lib/i18n/index.svelte': runeModule('./i18n/index.svelte.ts', 'server')
	};
	function component(path: string): string {
		let code = compile(readFileSync(new URL(path, import.meta.url), 'utf8'), { generate: 'server', filename: path }).js.code;
		code = code.replace(/(['"])(svelte(?:\/[^'"]*)?)\1/g, (_, _quote, name) => JSON.stringify(import.meta.resolve(name)));
		for (const [name, target] of Object.entries(aliases)) code = code.replaceAll(`'${name}'`, JSON.stringify(target));
		return dataModule(code);
	}
	aliases['./RangeDdlBody.svelte'] = component('./components/RangeDdlBody.svelte');
	aliases['./Tooltip.svelte'] = component('./components/Tooltip.svelte');
	const Viewer = (await import(component('./components/DdlViewer.svelte'))).default;
	const ddl = '［構図］右下（横2/3〜1、縦2/3〜1）に、赤い円。';
	const folded = render(Viewer, { props: { ddl, ranges, label: 'DDL', onPaint() {} } }).body;
	assert.match(folded, /range-name[^>]*folded/);
	assert.doesNotMatch(folded, /［構図］|横2\/3/);
	assert.match(folded, /指示書から描画/);
	const fallback = render(Viewer, { props: { ddl, ranges: [], label: 'DDL' } }).body;
	assert.match(fallback, /［構図］/);
	assert.match(fallback, /2\/3/);
	assert.equal(ddl, '［構図］右下（横2/3〜1、縦2/3〜1）に、赤い円。');
	for (const unmatched of [
		'［構図］右下（横0〜1/3、縦0〜1/3）に、赤い円。',
		'A circle at [composition] the bottom right (horizontal 0 to 1/3, vertical 0 to 1/3).'
	]) {
		const shown = render(Viewer, { props: { ddl: unmatched, ranges, label: 'DDL' } }).body;
		assert.equal(shown.replace(/<[^>]*>/g, '').split('DDL')[1].trim(), unmatched);
	}
	const invalid = render(Viewer, { props: { ddl: '右下（横1〜0、縦0〜1）に、円。', ranges, label: 'DDL', onPaint() {} } }).body;
	assert.match(invalid, /<button[^>]*disabled[^>]*>[^<]*指示書から描画/);
});

test('the existing replay action reserves one drawing before awaiting its saved parent', async () => {
	const source = readFileSync(new URL('./features/work/state.svelte.ts', import.meta.url), 'utf8');
	const ast = ts.createSourceFile('state.svelte.ts', source, ts.ScriptTarget.Latest, true);
	const functions: string[] = [];
	function visit(node: ts.Node) {
		if (ts.isFunctionDeclaration(node) && ['replay', 'replayOnce'].includes(node.name?.text ?? '')) functions.push(node.getText(ast));
		ts.forEachChild(node, visit);
	}
	visit(ast);
	assert.equal(functions.length, 2);
	// Execute the real action functions with the parent lookup held pending.
	const harness = `export function setup(ensureVisibleLineageParentId, authorDdl) {
		let replayStarting = false, ddl = 'edited numeric DDL', ddlGeneratedBaseline = 'saved DDL', reloading = false;
		let reloadError, pendingCanvasAspectDerivation = null, lineageDetached = false;
		let displayedHistoryItem = { lineage_node_id: 'parent' }, result = null, input = 'source';
		let replayAbortController, replayStopRequested, elapsedStage1Ms, elapsedStage2Ms, elapsedTotalMs;
		let tokensInStage1, tokensOutStage1, tokensInStage2, tokensOutStage2, stageLabel;
		const hasDdlBody = () => true, submitWouldRefine = () => false, resetTargetScopedState = () => {};
		const currentRefineParent = () => null, confirmFallbackRefine = async () => true;
		const effectiveCanvasAspectId = () => 'square', startTimer = () => {}, stopTimer = () => {};
		const deps = { history: () => ({ clearSelection() {} }) }, t = () => ({ stageStructuring: () => '' });
		${functions.join('\n')}
		return replay;
	}`;
	const code = ts.transpileModule(harness, { compilerOptions: { target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.ESNext } }).outputText;
	const { setup } = await import(dataModule(code));
	let release!: () => void;
	const parent = new Promise<void>((resolve) => release = resolve);
	const drawings: { ddl: string; kind: string }[] = [];
	const replay = setup(() => parent, async (ddl: string, options: { derivationKind: string }) => { drawings.push({ ddl, kind: options.derivationKind }); return {}; });
	const first = replay();
	await replay();
	assert.equal(drawings.length, 0);
	release();
	await first;
	assert.deepEqual(drawings, [{ ddl: 'edited numeric DDL', kind: 'ddl_edit' }]);
});
