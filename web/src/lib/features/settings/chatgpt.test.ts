import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { compile, compileModule } from 'svelte/compiler';
import { render } from 'svelte/server';
import { ja } from '../../i18n/ja';
import ts from 'typescript';

// Execute the actual rune controller, without a browser or a real account.
const source = ts.transpileModule(readFileSync(new URL('./chatgpt.svelte.ts', import.meta.url), 'utf8'), {
	compilerOptions: { target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.ESNext }
}).outputText;
const generated = compileModule(source, { filename: 'chatgpt.svelte.js', generate: 'client' }).js.code
	.replace(/(['"])svelte\/internal\/client\1/g, JSON.stringify(import.meta.resolve('svelte/internal/client')));
const { createChatGPTSettings } = await import('data:text/javascript;base64,' + Buffer.from(generated).toString('base64'));

const response = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
const state = (label: string) => ({ available: true, reason: null, self_hosted: true, active_profile_id: 'profile', profiles: [{ id: 'profile', label, state: 'connected' }] });

test('self-hosted authorization opens the Mac helper with only the current owner and requested action', async () => {
	const owner = '00000000-0000-4000-8000-000000000001';
	const profile = '00000000-0000-4000-8000-000000000002';
	const launched: string[] = [];
	const previous = globalThis.window;
	(globalThis as any).window = { location: { assign: (url: string) => launched.push(url) } };
	try {
		const connection = createChatGPTSettings({
			owner: () => owner, available: () => true, invalidate() {}, changed() {},
			apiFetch: async () => response({ action: 'local_helper' })
		});
		await connection.authorize(profile, true);
		assert.equal(launched.length, 1);
		const url = new URL(launched[0]);
		assert.equal(url.protocol, 'inku-chatgpt:');
		assert.equal(url.hostname, 'connect');
		assert.deepEqual([...url.searchParams], [['owner_id', owner], ['consent', '1'], ['profile_id', profile]]);
		assert.equal(connection.helperUrl, url.href);
		assert.equal(connection.busy, false);
		connection.reset();
		assert.equal(connection.helperUrl, null);
	} finally { (globalThis as any).window = previous; }
});

test('owner changes hide saved profiles and discard a late response; unconfirmed revocation stays visible', async () => {
	let owner = 'A', available = true, changes = 0;
	let deferred: ((response: Response) => void) | undefined;
	let slow = false;
	const connection = createChatGPTSettings({
		owner: () => owner, available: () => available, invalidate() {}, changed() { changes++; },
		apiFetch: async (url: string) => url.endsWith('sign-out')
			? response({ status: 'signed_out', revocation_confirmed: false })
			: slow ? new Promise<Response>((resolve) => { deferred = resolve; }) : response(state(owner))
	});
	await connection.load();
	assert.equal(connection.state.profiles[0].label, 'A');
	slow = true;
	const old = connection.load();
	await Promise.resolve();
	owner = 'B';
	assert.equal(connection.state, null);
	deferred!(response(state('A')));
	await old;
	assert.equal(connection.state, null);
	slow = false;
	await connection.load();
	await connection.signOut('profile');
	assert.equal(connection.code, 'chatgpt_revocation_unconfirmed');
	assert.equal(changes, 1);
	available = false;
	assert.equal(connection.state, null);
	assert.equal(connection.code, null);
	connection.reset();
});

test('refresh models shows progress, offered names and selection entry, or an empty result and safe failure', async () => {
	const viewSource = readFileSync(new URL('./ChatGPTSettings.svelte', import.meta.url), 'utf8')
		.replace("import { t } from '$lib/i18n/index.svelte';", `import { ja } from ${JSON.stringify(new URL('../../i18n/ja.ts', import.meta.url).href)}; const t = () => ja;`);
	const viewCode = compile(viewSource, { filename: 'ChatGPTSettings.svelte', generate: 'server' }).js.code
		.replace(/(['"])svelte\/internal\/server\1/g, JSON.stringify(import.meta.resolve('svelte/internal/server')))
		.replace(/(['"])svelte\1/g, JSON.stringify(import.meta.resolve('svelte')));
	const view = (await import('data:text/javascript;base64,' + Buffer.from(viewCode).toString('base64'))).default;
	let deferred: ((value: Response) => void) | undefined;
	let changes = 0, owner = 'owner';
	const connected = { ...state('Account'), profiles: [{ id: 'profile', label: 'Account', state: 'connected', generation: 1, scopes: ['chatgpt.tokens.use.direct'] }] };
	const connection = createChatGPTSettings({
		owner: () => owner, available: () => true, invalidate() {}, changed() { changes++; },
		apiFetch: async (url: string) => url.endsWith('/models/refresh')
			? new Promise<Response>((resolve) => { deferred = resolve; }) : response(connected)
	});
	// Rendering a snapshot keeps SSR's destroy hook from cancelling the controller under test.
	const body = () => render(view, { props: { connection: {
		state: connection.state, code: connection.code, busy: connection.busy, models: connection.models,
		load() {}, cancel() {}
	}, onOpenModelSelection() {} } }).body;
	await connection.load();
	const pending = connection.refreshModels();
	assert.equal(connection.code, 'chatgpt_models_loading');
	assert.match(body(), new RegExp(ja.chatgptStatus('chatgpt_models_loading')));
	const models = [{ id: 'second-slug', label: 'First offered' }, { id: 'first-slug', label: 'Second offered' }];
	deferred!(response({ profile_id: 'profile', generation: 1, models }));
	await pending;
	assert.deepEqual(connection.models, models);
	const listed = body();
	assert.match(listed, new RegExp(ja.chatgptModelsLoaded(2)));
	assert.ok(listed.indexOf('First offered') < listed.indexOf('Second offered'));
	assert.match(listed, new RegExp(ja.modelSelectButton));
	assert.equal(changes, 1);
	owner = 'other';
	assert.equal(connection.models, null);
	owner = 'owner';

	const empty = connection.refreshModels();
	deferred!(response({ profile_id: 'profile', generation: 1, models: [] }));
	await empty;
	assert.match(body(), new RegExp(ja.chatgptModelsEmpty));
	assert.doesNotMatch(body(), new RegExp(ja.modelSelectButton));
	assert.equal(changes, 2);

	const failed = connection.refreshModels();
	deferred!(new Response(JSON.stringify({ detail: { code: 'chatgpt_transport_unavailable' } }), { status: 503 }));
	await failed;
	assert.equal(connection.models, null);
	assert.match(body(), new RegExp(ja.chatgptStatus('chatgpt_transport_unavailable')));
	assert.equal(connection.busy, false);
	assert.equal(changes, 2);
	connection.reset();
});
