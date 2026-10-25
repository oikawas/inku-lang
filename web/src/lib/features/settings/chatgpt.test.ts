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
		.replace(/(['"])\$lib\/modelMeta\1/g, JSON.stringify(new URL('../../modelMeta.ts', import.meta.url).href))
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
				if (init?.method === 'PUT') {
					const body = JSON.parse(String(init.body));
					// A ChatGPT assessment is shared model settings, saved whole for the model that changed.
					if (body.providers?.chatgpt) {
						assert.deepEqual(body, { providers: { chatgpt: { models: [{ id: 'second-slug', label: 'First offered', recommendation_vision: 3, comment_ja: '共通の評価' }] } } });
						return response({ catalog: [], settings: { providers: {} } });
					}
					assert.deepEqual(Object.keys(body.providers), ['openai']);
				}
				return response({ catalog: [{ id: 'openai', label: 'OpenAI', models: [] }], settings: {
					providers: { openai: { base_url: '', api_key_set: false, api_key_hint: null, enabled_models: {} } }
				} });
			}
			assert.ok(path.startsWith('/api/me/chatgpt/'));
			if (path.endsWith('/refresh')) return new Promise<Response>((resolve) => { deferred = resolve; });
			if (init?.method === 'PUT') {
				const body = JSON.parse(String(init.body));
				assert.deepEqual(body, { profile_id: 'profile', generation: 1, published_models: ['second-slug'],
					model_purposes: { 'second-slug': ['vision'], 'first-slug': [] } });
				saved = { ...saved, models: [{ id: 'second-slug', label: 'First offered', purposes: ['vision'], enabled: true,
					recommendation_stage1: 4, comment_ja: '実測の評価' },
					{ id: 'first-slug', label: 'Second offered', purposes: [], enabled: false }], enabled_models: { 'second-slug': true, 'first-slug': false } };
			}
			return response(saved);
		}
	});
	await administration.loadModelSettings();
	assert.deepEqual(administration.modelCatalog.map((provider: any) => provider.id), ['chatgpt']);
	const pending = administration.fetchProviderModels('chatgpt');
	assert.equal(administration.modelSettingsLoading, true);
	assert.equal(administration.modelFetchResults.chatgpt.message, ja.chatgptStatus('chatgpt_models_loading'));
	saved = { ...saved, models: [{ id: 'second-slug', label: 'First offered', speed_label: 'Old speed' }, { id: 'first-slug', label: 'Second offered' }], enabled_models: { 'second-slug': false, 'first-slug': false } };
	deferred!(response(saved));
	await pending;
	assert.deepEqual(administration.modelCatalog[0].models.map((model: any) => model.id), ['second-slug', 'first-slug']);
	assert.deepEqual(administration.modelCatalog[0].models[0].purposes, ['llm', 'vision']);
	assert.equal(administration.modelFetchResults.chatgpt.message, ja.chatgptModelsLoaded(2));
	assert.equal(await administration.saveModelProvider('chatgpt', { models: [
		{ id: 'second-slug', label: 'First offered', purposes: ['vision'], recommendation_stage1: 4, speed_label: '', comment_ja: '実測の評価' },
		{ id: 'first-slug', label: 'Second offered', purposes: [] }
	], enabled_models: { 'second-slug': true, 'first-slug': false } }), true);
	assert.equal(administration.modelSettings.providers.chatgpt.enabled_models['second-slug'], true);
	assert.deepEqual(administration.modelCatalog[0].models[0].purposes, ['vision']);
	assert.equal(administration.modelCatalog[0].models[0].recommendation_stage1, 4);
	assert.equal(administration.modelCatalog[0].models[0].comment_ja, '実測の評価');
	assert.equal(administration.modelCatalog[0].models[0].speed_label, undefined);
	assert.deepEqual(administration.modelSettings.providers.chatgpt.models[1].purposes, []);
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
	const before = requests.length;
	assert.equal(await administration.saveModelProvider('chatgpt', { models: [
		{ id: 'second-slug', label: 'First offered', purposes: ['vision'], recommendation_vision: 3, comment_ja: '共通の評価' },
		{ id: 'first-slug', label: 'Second offered', purposes: [] }
	], enabled_models: { 'second-slug': true, 'first-slug': false } }), true);
	assert.deepEqual(requests.slice(before).map((request) => request.path), ['/api/settings/models', '/api/me/chatgpt/models/settings']);
	await administration.saveModelSettings();
	assert.equal(administration.modelSettings.providers.chatgpt.enabled_models['second-slug'], true);
	assert.equal(changes, 4);
	admin = false;
	assert.deepEqual(administration.modelCatalog.map((provider: any) => provider.id), ['chatgpt']);
	assert.deepEqual(Object.keys(administration.modelSettings.providers), ['chatgpt']);
	available = false;
	assert.deepEqual(administration.modelCatalog, []);
	assert.deepEqual(administration.modelSettings.providers, {});
	administration.resetForLoggedOut();
	connection.reset();
});

test('personal publication picker exposes Vision use; the shared assessments are an administrator\'s to edit', async () => {
	const source = readFileSync(new URL('./ModelAdministrationSettings.svelte', import.meta.url), 'utf8')
		.replace("import { t } from '$lib/i18n/index.svelte';", `import { ja } from ${JSON.stringify(new URL('../../i18n/ja.ts', import.meta.url).href)}; const t = () => ja;`)
		.replace("from '$lib/modelMeta'", `from ${JSON.stringify(new URL('../../modelMeta.ts', import.meta.url).href)}`)
		.replace("import './model-administration-settings.css';", '')
		// Open the existing dialog in the SSR fixture, without changing production props.
		.replace('</script>', "openModelPicker('chatgpt');\n</script>");
	const generated = compile(source, { filename: 'ModelAdministrationSettings.svelte', generate: 'server' }).js.code
		.replace(/(['"])svelte\/internal\/server\1/g, JSON.stringify(import.meta.resolve('svelte/internal/server')))
		.replace(/(['"])svelte\1/g, JSON.stringify(import.meta.resolve('svelte')));
	const view = (await import('data:text/javascript;base64,' + Buffer.from(generated).toString('base64'))).default;
	const models = [{ id: 'vision-model', label: 'Vision model', purposes: ['vision'], speed_label: 'Upstream speed', comment_ja: '接続元の評価' },
		{ id: 'no-purpose', label: 'Unused model', purposes: [] }];
	const picker = (personalOnly: boolean) => render(view, { props: {
		providerGroups: [{ id: 'chatgpt', label: ja.chatgptPlanLabel, models }], personalOnly,
		administration: { modelSettings: { providers: { chatgpt: { enabled_models: { 'vision-model': true, 'no-purpose': false } } } },
			modelFetchResults: {}, modelSettingsLoading: false }
	} }).body;
	const body = picker(true);
	assert.match(body, /<option value="vision">/);
	assert.match(body, /aria-label="Vision model LLM \/ Vision"/);
	assert.match(body, /aria-pressed="true"[^>]*>Vision<\/button>/);
	const unused = body.slice(body.indexOf('Unused model') - 150, body.indexOf('Unused model'));
	assert.match(unused, /disabled/);
	// Assessments are shared model settings (2026-10-13): a person publishes, an administrator assesses.
	assert.doesNotMatch(body, /<details class="model-metadata-editor">/);
	const administrator = picker(false);
	assert.match(administrator, /<details class="model-metadata-editor">/);
	assert.match(administrator, /Upstream speed/);
	assert.match(administrator, /接続元の評価/);
	for (const key of ['recommendation_llm', 'recommendation_vision'] as const) assert.ok(administrator.includes(ja.settingsModelRecommendationFields[key]));
	assert.ok(!administrator.includes(ja.settingsModelRecommendationFields.recommendation_stage1));
	assert.match(administrator, /平均秒数 Vision/);
});

test('delete posts to the registration, and a return from the Mac helper re-reads the state', async () => {
	const owner = '00000000-0000-4000-8000-000000000001';
	const id = '00000000-0000-4000-8000-000000000002';
	const calls: string[] = [];
	let current: unknown = { ...state('Account'), profiles: [{ id, label: 'Account', state: 'signed_out', generation: 2, scopes: [] }] };
	let changes = 0;
	const previous = globalThis.window;
	(globalThis as any).window = { location: { assign() {} } };
	try {
		const connection = createChatGPTSettings({
			owner: () => owner, available: () => true, invalidate() {}, changed() { changes++; },
			apiFetch: async (url: string) => {
				calls.push(url);
				if (url.endsWith('/authorize')) return response({ action: 'local_helper' });
				if (url.endsWith('/delete')) { current = { ...state('Account'), active_profile_id: null, profiles: [] }; return response({ status: 'deleted', revocation_confirmed: true }); }
				return response(current);
			}
		});
		await connection.load();
		await connection.recheck();
		assert.equal(calls.length, 1, 'no helper was opened, so a return does not re-read');
		await connection.authorize(id);
		assert.equal(connection.code, 'chatgpt_helper_requested');
		current = { ...state('Account'), profiles: [{ id, label: 'Account', state: 'connected', generation: 3, scopes: ['chatgpt.tokens.use.direct'] }] };
		await connection.recheck();
		assert.equal(connection.state.profiles[0].state, 'connected');
		assert.equal(connection.code, 'chatgpt_helper_requested');
		assert.ok(connection.helperUrl);
		assert.equal(changes, 1);
		await connection.recheck();
		assert.equal(changes, 1, 'an unchanged state does not reload the model lists');
		await connection.remove(id);
		assert.ok(calls.some((url) => url === '/api/me/chatgpt/profiles/' + id + '/delete'));
		assert.deepEqual(connection.state.profiles, []);
		assert.equal(connection.code, null);
	} finally { (globalThis as any).window = previous; }
});
