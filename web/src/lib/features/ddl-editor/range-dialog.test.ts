import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { compile, compileModule } from 'svelte/compiler';
import { render } from 'svelte/server';
import ts from 'typescript';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const dataModule = (code: string) => 'data:text/javascript;base64,' + Buffer.from(code).toString('base64');
const imports = (code: string) => code.replace(/(['"])(svelte(?:\/[^'"]*)?)\1/g, (_, _quote, name) => JSON.stringify(import.meta.resolve(name)));

test('the actual dialog preview renders its image and relative frame, with a new-work fallback', async () => {
	const source = ts.transpileModule(read('../../i18n/index.svelte.ts'), { compilerOptions: { target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.ESNext } }).outputText;
	const pack = dataModule(imports(compileModule(source, { filename: 'index.svelte.js', generate: 'server' }).js.code)
		.replaceAll("'./ja'", JSON.stringify(new URL('../../i18n/ja.ts', import.meta.url).href))
		.replaceAll("'./en'", JSON.stringify(new URL('../../i18n/en.ts', import.meta.url).href)));
	const component = dataModule(imports(compile(read('../../components/DdlRangePreview.svelte'), { filename: 'DdlRangePreview.svelte', generate: 'server' }).js.code)
		.replaceAll("'$lib/i18n/index.svelte'", JSON.stringify(pack)));
	const Preview = (await import(component)).default;
	const body = render(Preview, { props: { artworkUrl: '/api/history/selected/svg', preview: { bounds: [0.2, 0.3, 0.7, 0.9], invalid: true } } }).body;
	assert.match(body, /src="\/api\/history\/selected\/svg"/);
	assert.match(body, /class="ddl-range-frame [^"]*\binvalid\b/);
	for (const [key, value] of [['left', 20], ['top', 30], ['width', 50], ['height', 60]] as const) {
		const percent = Number(body.match(new RegExp(`${key}: ([\\d.]+)%`))![1]);
		assert.ok(Math.abs(percent - value) < 1e-8, `${key} follows the artwork's relative bounds`);
	}
	assert.match(body, /下線の名前/);
	const fresh = render(Preview, { props: {} }).body;
	assert.doesNotMatch(fresh, /<img|ddl-range-frame/);
	assert.match(fresh, /描画後/);
	const page = read('../../../routes/+page.svelte');
	const dialog = page.slice(page.indexOf('<DdlEditorDialog'), page.indexOf('/>', page.indexOf('<DdlEditorDialog')));
	assert.match(dialog, /ranges=\{compositionRanges\}/);
	assert.match(dialog, /encodeURIComponent\(ddlDialogNode\.history\.id\)/, 'the miniature belongs to the selected work, not the blurred canvas');
});

test('the dialog draw handler passes complete numeric source and blocks invalid/IME edits', async () => {
	const dialog = read('../../components/DdlEditorDialog.svelte');
	const ast = ts.createSourceFile('dialog.ts', dialog.slice(dialog.indexOf('<script lang="ts">') + 18, dialog.indexOf('</script>')), ts.ScriptTarget.Latest, true);
	const draw = ast.statements.find((node) => ts.isFunctionDeclaration(node) && node.name?.text === 'requestDraw')!.getText(ast);
	const harness = `export function setup(value, rangeStatus, onDraw) {
		let drawing = false, drawController = null, importedPlugins = [], mode = 'edit';
		${draw}
		return requestDraw;
	}`;
	const code = ts.transpileModule(harness, { compilerOptions: { target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.ESNext } }).outputText;
	const { setup } = await import(dataModule(code));
	const raw = '  紙。\n右下（横2/3〜1、縦2/3〜1）に、赤い円。  ';
	const drawn: string[] = [];
	const record = (ddl: string) => drawn.push(ddl);
	await setup(raw, { invalid: false, composing: false }, record)();
	for (const status of [{ invalid: true, composing: false }, { invalid: false, composing: true }]) await setup(raw, status, record)();
	assert.deepEqual(drawn, [raw]);
	assert.match(dialog, /onRanges=\{\(status\) => \(rangeStatus = status\)\}/);
	assert.match(dialog, /event\.isComposing \|\| event\.defaultPrevented/);
});
