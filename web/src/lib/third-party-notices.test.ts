import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { compile, compileModule } from 'svelte/compiler';
import { render } from 'svelte/server';
import ts from 'typescript';
import { EMPTY_NOTICE_STATE, NoticeReader, type NoticeState } from './third-party-notices.ts';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const manifest = JSON.parse(read('../../static/licenses/manifest.json'));
const legal = read('../../../server/src/inku_server/notices/sudachidict-small-20260723.1-LEGAL.txt');
const server = { components: [{ id: 'sudachidict-small', group: 'resources', name: 'SudachiDict Small / UniDic',
	version: '20260723.1', license: 'Apache-2.0 / BSD',
	source: 'https://github.com/WorksApplications/SudachiDict/blob/3e49051e71011cac7d74df779e80ef1dab818e56/LEGAL' }] };
const baseFetch: typeof fetch = async (url) => {
	if (url === '/licenses/manifest.json') return Response.json(manifest);
	if (url === '/api/notices') return Response.json(server);
	if (url === '/api/notices/sudachidict-small') return new Response(legal);
	if (String(url).startsWith('/licenses/')) return new Response(read(`../../static${url}`));
	throw new Error('Unexpected URL');
};

test('the reviewed Web manifest and bundled UniDic full text are reachable through the reader', async () => {
	const reader = new NoticeReader(baseFetch, () => {});
	await reader.load();
	assert.deepEqual(reader.state.failedGroups, []);
	assert.equal(reader.state.components.filter((item) => item.group === 'web').length, Object.keys(manifest.packages).length);
	assert.match(reader.state.text, /MIT License/);
	await reader.select('server:sudachidict-small');
	assert.equal(reader.state.text, legal);
	assert.match(reader.state.text, /The UniDic Consortium/);
	await reader.select('web:@codemirror/view');
	assert.equal(reader.state.text, read('../../static/licenses/codemirror-view-MIT.txt'));
	reader.dispose();
});

test('a failed Server catalog does not hide Web notices and a failed text can be retried', async () => {
	let failCatalog = true, failText = true;
	const fetcher: typeof fetch = async (url, options) => {
		if (url === '/api/notices' && failCatalog) return new Response('', { status: 503 });
		if (url === '/api/notices/sudachidict-small' && failText) return new Response('<html>fallback</html>', { headers: { 'content-type': 'text/html' } });
		return baseFetch(url, options);
	};
	const reader = new NoticeReader(fetcher, () => {});
	await reader.load();
	assert.deepEqual(reader.state.failedGroups, ['server']);
	await reader.select('web:svelte');
	assert.equal(reader.state.text, read('../../static/licenses/svelte-MIT.txt'));
	failCatalog = false;
	await reader.load();
	assert.deepEqual(reader.state.failedGroups, []);
	await reader.select('server:sudachidict-small');
	assert.equal(reader.state.textFailed, true);
	assert.equal(reader.state.text, '');
	failText = false;
	await reader.select('server:sudachidict-small');
	assert.equal(reader.state.textFailed, false);
	assert.equal(reader.state.text, legal);
	reader.dispose();
});

test('an old text response cannot replace a newer selection or update a closed reader', async () => {
	let finish!: (response: Response) => void;
	const fetcher: typeof fetch = async (url, options) => url === '/api/notices/sudachidict-small'
		? new Promise<Response>((resolve) => { finish = resolve; }) : baseFetch(url, options);
	let changes = 0;
	const reader = new NoticeReader(fetcher, () => { changes++; });
	await reader.load();
	const old = reader.select('server:sudachidict-small');
	await reader.select('web:svelte');
	const latest = reader.state.text;
	finish(new Response(legal));
	await old;
	assert.equal(reader.state.selectedId, 'web:svelte');
	assert.equal(reader.state.text, latest);
	const closing = reader.select('server:sudachidict-small');
	reader.dispose();
	const count = changes;
	finish(new Response(legal));
	await closing;
	assert.equal(changes, count);
});

test('the real information entry and Swift-style notice dialog render selectable, escaped full text', async () => {
	const dataModule = (code: string) => 'data:text/javascript;base64,' + Buffer.from(code).toString('base64');
	const imports = (code: string) => code.replace(/(['"])(svelte(?:\/[^'"]*)?)\1/g, (_, _quote, name) => JSON.stringify(import.meta.resolve(name)));
	const source = ts.transpileModule(read('./i18n/index.svelte.ts'), { compilerOptions: { target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.ESNext } }).outputText;
	const pack = dataModule(imports(compileModule(source, { filename: 'index.svelte.js', generate: 'server' }).js.code)
		.replaceAll("'./ja'", JSON.stringify(new URL('./i18n/ja.ts', import.meta.url).href))
		.replaceAll("'./en'", JSON.stringify(new URL('./i18n/en.ts', import.meta.url).href)));
	const body = compile(read('./components/ThirdPartyNoticesDialog.svelte'), { filename: 'ThirdPartyNoticesDialog.svelte', generate: 'server' }).js.code;
	const Dialog = (await import(dataModule(imports(body)
		.replaceAll("'$lib/i18n/index.svelte'", JSON.stringify(pack))
		.replaceAll("'$lib/third-party-notices'", JSON.stringify(new URL('./third-party-notices.ts', import.meta.url).href))))).default;
	const page = read('../routes/+page.svelte');
	const entry = page.match(/<section class="app-info-licenses">[\s\S]*?<\/section>/)![0];
	const Entry = (await import(dataModule(imports(compile(`<script>import { t } from ${JSON.stringify(pack)}; let noticesButton; const openNotices = () => {};</script>${entry}`,
		{ filename: 'AboutLicenses.svelte', generate: 'server' }).js.code)))).default;
	const reader = new NoticeReader(baseFetch, () => {});
	await reader.load();
	await reader.select('server:sudachidict-small');
	const state: NoticeState = { ...reader.state, text: legal + '\n<test-notice> & literal' };
	const props = { state, onClose() {}, onSelect() {}, onReload() {}, onRetryText() {} };
	const rendered = render(Dialog, { props }).body;
	assert.match(render(Entry).body, /第三者ライセンスを表示/);
	assert.match(render(Entry).body, /MIT License/);
	assert.match(rendered, /Webパッケージ/);
	assert.match(rendered, /同梱の辞書とフォント/);
	assert.match(rendered, /role="dialog"/);
	assert.match(rendered, /aria-pressed="true"/);
	assert.match(rendered, /The UniDic Consortium/);
	assert.ok(rendered.includes('&lt;test-notice> &amp; literal'), 'the literal tag opener and ampersand remain text');
	assert.doesNotMatch(rendered, /<test-notice>/);
	const failed = render(Dialog, { props: { ...props, state: { ...state, text: '', textFailed: true, failedGroups: ['server'] } } }).body;
	assert.match(failed, /取得できた項目は読めます/);
	assert.match(failed, /通知の全文を読み込めません/);
	assert.match(failed, /再試行/);
	assert.match(render(Dialog, { props: { ...props, state: EMPTY_NOTICE_STATE } }).body, /読み込み中/);
	reader.dispose();
});
