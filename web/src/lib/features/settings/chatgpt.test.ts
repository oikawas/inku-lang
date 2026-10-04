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

test('self-hosted authorization keeps Brave and Japanese in the public Mac helper action', async () => {
	const owner = '00000000-0000-4000-8000-000000000001';
	const profile = '00000000-0000-4000-8000-000000000002';
	const launched: string[] = [];
	const previous = globalThis.window;
	const previousNavigator = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
	Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { brave: { isBrave: async () => true } } });
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
		assert.deepEqual([...url.searchParams], [['owner_id', owner], ['consent', '1'], ['profile_id', profile], ['browser', 'brave'], ['language', 'ja']]);
		assert.equal(ja.chatgptContinue, 'ChatGPTで続ける');
		assert.doesNotMatch(ja.chatgptLocalHelperHint, /Chrome|helper|Continue with/);
		assert.equal(connection.helperUrl, url.href);
		assert.equal(connection.busy, false);
		connection.reset();
		assert.equal(connection.helperUrl, null);
	} finally {
		(globalThis as any).window = previous;
		if (previousNavigator) Object.defineProperty(globalThis, 'navigator', previousNavigator);
		else Reflect.deleteProperty(globalThis, 'navigator');
	}
});

test('only the fixed server-selected container target enters the helper URI', async () => {
	const owner = '00000000-0000-4000-8000-000000000001';
	const launched: string[] = [];
	const previous = globalThis.window;
	(globalThis as any).window = { location: { assign: (url: string) => launched.push(url) } };
	try {
		let helperTarget: string | undefined = 'container';
		const connection = createChatGPTSettings({
			owner: () => owner, available: () => true, invalidate() {}, changed() {},
			apiFetch: async () => response({ action: 'local_helper', helper_target: helperTarget })
		});
		await connection.authorize();
		assert.equal(new URL(launched[0]).searchParams.get('target'), 'container');
		helperTarget = undefined;
		await connection.authorize();
		assert.equal(new URL(launched[1]).searchParams.has('target'), false);
		helperTarget = 'https://arbitrary.example/command';
		await connection.authorize();
		assert.equal(launched.length, 2);
		assert.equal(connection.code, 'chatgpt_operation_failed');
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

test('connected guide leads to personal model settings with explicit publication and stale-owner protection', async () => {
	const viewSource = readFileSync(new URL('./ChatGPTSettings.svelte', import.meta.url), 'utf8')
		.replace("import { t } from '$lib/i18n/index.svelte';", `import { ja } from ${JSON.stringify(new URL('../../i18n/ja.ts', import.meta.url).href)}; const t = () => ja;`);
	const viewCode = compile(viewSource, { filename: 'ChatGPTSettings.svelte', generate: 'server' }).js.code
		.replace(/(['"])svelte\/internal\/server\1/g, JSON.stringify(import.meta.resolve('svelte/internal/server')))
		.replace(/(['"])svelte\1/g, JSON.stringify(import.meta.resolve('svelte')));
	const view = (await import('data:text/javascript;base64,' + Buffer.from(viewCode).toString('base64'))).default;
	let deferred: ((value: Response) => void) | undefined;
	let changes = 0, owner = 'owner', admin = false, available = true;
	const connected = { ...state('Account'), profiles: [{ id: 'profile', label: 'Account', state: 'connected', generation: 1, scopes: ['chatgpt.tokens.use.direct'] }] };
	const connection = createChatGPTSettings({
		owner: () => owner, available: () => true, invalidate() {}, changed() { changes++; },
		apiFetch: async () => response(connected)
	});
	// Rendering a snapshot keeps SSR's destroy hook from cancelling the controller under test.
	const body = () => render(view, { props: { connection: {
		state: connection.state, code: connection.code, busy: connection.busy,
		load() {}, cancel() {}
	}, onOpenModelSettings() {} } }).body;
	await connection.load();
	assert.match(body(), new RegExp(ja.chatgptModelSettingsGuide));
	assert.match(body(), new RegExp(ja.chatgptOpenModelSettings));
	assert.doesNotMatch(body(), new RegExp(ja.chatgptRefreshModels));

	const adminSource = ts.transpileModule(readFileSync(new URL('./model-administration.svelte.ts', import.meta.url), 'utf8')
		.replace("import { t } from '$lib/i18n/index.svelte';", `import { ja } from ${JSON.stringify(new URL('../../i18n/ja.ts', import.meta.url).href)}; const t = () => ja;`)
		.replace(/(['"])\$lib\/models\1/g, JSON.stringify(new URL('../../models.ts', import.meta.url).href)), {
		compilerOptions: { target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.ESNext }
	}).outputText;
	const adminCode = compileModule(adminSource, { filename: 'model-administration.svelte.js', generate: 'client' }).js.code
		.replace(/(['"])svelte\/internal\/client\1/g, JSON.stringify(import.meta.resolve('svelte/internal/client')));
	const { createModelAdministration } = await import('data:text/javascript;base64,' + Buffer.from(adminCode).toString('base64'));
	const requests: { path: string; body?: unknown }[] = [];
	let saved = { profile_id: 'profile', generation: 1, models: [] as any[], enabled_models: {} as Record<string, boolean> };
	const administration = createModelAdministration({
		currentUser: () => ({ id: owner, permission_groups: admin ? ['admins'] : ['users'] }), chatgptAvailable: () => available,
		loadAvailableModels() { changes++; }, requestConfirmation() {}, describeApiError() { return 'Error'; },
		apiFetch: async (path: string, init?: RequestInit) => {
			requests.push({ path, body: init?.body ? JSON.parse(String(init.body)) : undefined });
			if (path === '/api/settings/models') {
				assert.equal(admin, true);
				if (init?.method === 'PUT') assert.deepEqual(Object.keys(JSON.parse(String(init.body)).providers), ['openai']);
				return response({ catalog: [{ id: 'openai', label: 'OpenAI', models: [] }], settings: {
					providers: { openai: { base_url: '', api_key_set: false, api_key_hint: null, enabled_models: {} } }
				} });
			}
			assert.ok(path.startsWith('/api/me/chatgpt/'));
			if (path.endsWith('/refresh')) return new Promise<Response>((resolve) => { deferred = resolve; });
			if (init?.method === 'PUT') {
				const body = JSON.parse(String(init.body));
				assert.deepEqual(body, { profile_id: 'profile', generation: 1, published_models: ['second-slug'] });
				saved = { ...saved, enabled_models: { 'second-slug': true, 'first-slug': false } };
			}
			return response(saved);
		}
	});
	await administration.loadModelSettings();
	assert.deepEqual(administration.modelCatalog.map((provider: any) => provider.id), ['chatgpt']);
	const pending = administration.fetchProviderModels('chatgpt');
	assert.equal(administration.modelSettingsLoading, true);
	assert.equal(administration.modelFetchResults.chatgpt.message, ja.chatgptStatus('chatgpt_models_loading'));
	saved = { ...saved, models: [{ id: 'second-slug', label: 'First offered' }, { id: 'first-slug', label: 'Second offered' }], enabled_models: { 'second-slug': false, 'first-slug': false } };
	deferred!(response(saved));
	await pending;
	assert.deepEqual(administration.modelCatalog[0].models.map((model: any) => model.id), ['second-slug', 'first-slug']);
	assert.equal(administration.modelFetchResults.chatgpt.message, ja.chatgptModelsLoaded(2));
	assert.equal(await administration.saveModelProvider('chatgpt', { enabled_models: { 'second-slug': true, 'first-slug': false } }), true);
	assert.equal(administration.modelSettings.providers.chatgpt.enabled_models['second-slug'], true);
	assert.equal(changes, 2);
	const failed = administration.fetchProviderModels('chatgpt');
	deferred!(new Response(JSON.stringify({ detail: { code: 'chatgpt_transport_unavailable' } }), { status: 503 }));
	await failed;
	assert.equal(administration.modelFetchResults.chatgpt.type, 'error');
	assert.equal(administration.modelSettings.providers.chatgpt.enabled_models['second-slug'], true);
	const late = administration.fetchProviderModels('chatgpt');
	owner = 'other';
	assert.equal(administration.modelSettings, null);
	deferred!(response(saved));
	await late;
	assert.deepEqual(administration.modelCatalog, []);
	assert.equal(changes, 2);
	assert.equal(requests.filter((request) => request.body && (request.body as any).published_models).length, 1);
	administration.resetForLoggedOut();
	owner = 'owner'; admin = true;
	await administration.loadModelSettings();
	assert.deepEqual(administration.modelCatalog.map((provider: any) => provider.id), ['openai', 'chatgpt']);
	await administration.saveModelSettings();
	assert.equal(administration.modelSettings.providers.chatgpt.enabled_models['second-slug'], true);
	assert.equal(changes, 3);
	admin = false;
	assert.deepEqual(administration.modelCatalog.map((provider: any) => provider.id), ['chatgpt']);
	assert.deepEqual(Object.keys(administration.modelSettings.providers), ['chatgpt']);
	available = false;
	assert.deepEqual(administration.modelCatalog, []);
	assert.deepEqual(administration.modelSettings.providers, {});
	administration.resetForLoggedOut();
	connection.reset();
});
