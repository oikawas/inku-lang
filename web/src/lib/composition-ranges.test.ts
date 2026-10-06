import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { compile, compileModule } from 'svelte/compiler';
import { render } from 'svelte/server';
import ts from 'typescript';
import { editNumericRange, matchingRange, parseRangeBody, readCompositionRanges, scanNumericRanges } from './composition-ranges.ts';
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

test('the actual viewer SSR uses the common editor and keeps its full-source draw guards', async () => {
	const aliases: Record<string, string> = {
		'$lib/composition-ranges': new URL('./composition-ranges.ts', import.meta.url).href,
		'$lib/ddl-source': new URL('./ddl-source.ts', import.meta.url).href,
		'$lib/instructionLang': new URL('./instructionLang.ts', import.meta.url).href,
		'$lib/plugin-names': new URL('./plugin-names.ts', import.meta.url).href,
		'$lib/saijiki': new URL('./saijiki.ts', import.meta.url).href,
		'$lib/features/ddl-editor/codemirror': new URL('./features/ddl-editor/codemirror.ts', import.meta.url).href,
		'$lib/i18n/index.svelte': runeModule('./i18n/index.svelte.ts', 'server')
	};
	function component(path: string): string {
		let code = compile(readFileSync(new URL(path, import.meta.url), 'utf8'), { generate: 'server', filename: path }).js.code;
		code = code.replace(/(['"])(svelte(?:\/[^'"]*)?)\1/g, (_, _quote, name) => JSON.stringify(import.meta.resolve(name)));
		for (const [name, target] of Object.entries(aliases)) code = code.replaceAll(`'${name}'`, JSON.stringify(target));
		return dataModule(code);
	}
	aliases['./Tooltip.svelte'] = component('./components/Tooltip.svelte');
	aliases['./SaijikiInline.svelte'] = component('./components/SaijikiInline.svelte');
	aliases['./DdlEditor.svelte'] = component('./components/DdlEditor.svelte');
	const Viewer = (await import(component('./components/DdlViewer.svelte'))).default;
	const ddl = '  紙。\r\n右下（横2/3〜1、縦2/3〜1）に、赤い円。  ';
	const props = { ddl, ranges, label: 'DDL', onPaint() {}, onEdit() {}, previewForWord() {}, previewForPlugin() {} };
	const box = render(Viewer, { props }).body;
	assert.match(box, /class="ddl-editor[^"]*\bcompact\b/);
	assert.match(box, /class="ddl-editor-frame[^"]*\breadonly\b/);
	assert.doesNotMatch(box, /ddl-editor-toolbar|ddl-editor-vocabulary|ddl-editor-guide/);
	assert.match(box, /指示書エディタ/);
	assert.match(box, /指示書から描画/);
	const source = readFileSync(new URL('./components/DdlViewer.svelte', import.meta.url), 'utf8');
	assert.match(source, /value=\{ddl\}/, 'CodeMirror gets the complete source, even with an empty range table');
	assert.doesNotMatch(source, /RangeDdlBody|highlightDDL/);
	const editable = render(Viewer, { props: { ...props, onDdlChange() {} } }).body;
	assert.doesNotMatch(editable, /ddl-editor-frame[^"]*\breadonly\b/);
	const fallback = render(Viewer, { props: { ...props, ranges: [] } }).body;
	assert.match(fallback, /ddl-editor-frame/);
	assert.equal(ddl, '  紙。\r\n右下（横2/3〜1、縦2/3〜1）に、赤い円。  ');
	const invalid = render(Viewer, { props: { ...props, ddl: '右下（横1〜0、縦0〜1）に、円。' } }).body;
	assert.match(invalid, /<button[^>]*disabled[^>]*>[^<]*指示書から描画/);
	assert.match(invalid, /0〜1/);
	const empty = render(Viewer, { props: { ...props, ddl: ' \r\n' } }).body;
	assert.match(empty, /<button[^>]*disabled[^>]*>[^<]*指示書から描画/);
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
