import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { test } from 'node:test';

const libRoot = new URL('../../', import.meta.url);
registerHooks({
	resolve(specifier, context, nextResolve) {
		if (specifier.startsWith('$lib/')) return nextResolve(new URL(`${specifier.slice(5)}.ts`, libRoot).href, context);
		if (specifier.startsWith('.') && !/\.[a-z]+$/i.test(specifier)) return nextResolve(`${specifier}.ts`, context);
		return nextResolve(specifier, context);
	}
});
const identity = <T>(value: T): T => value;
(globalThis as unknown as Record<string, unknown>).$state = Object.assign(identity, { raw: identity });
const { createModelAdministration } = await import('./model-administration.svelte.ts');

test('provider rate limits reach the save request and retain the authoritative values on failure', async () => {
	let limits = { rpm: 30, tpm: 16000, rpd: 14400 };
	let refuse = false;
	const saved: unknown[] = [];
	const response = () => ({
		catalog: [{ id: 'gemini', label: 'Gemini', kind: 'gemini', models: [] }],
		settings: { providers: { gemini: {
			base_url: 'https://provider.invalid', api_key_set: true, api_key_hint: '***',
			enabled_models: {}, rate_limits: limits
		} } }
	});
	const administration = createModelAdministration({
		currentUser: () => ({ permission_groups: ['admins'] }),
		apiFetch: async (path, init) => {
			assert.equal(path, '/api/settings/models');
			if (init?.method === 'PUT') {
				const body = JSON.parse(String(init.body));
				saved.push(body.providers.gemini.rate_limits);
				assert.equal(body.providers.gemini.api_key, undefined);
				if (refuse) return new Response('{}', { status: 500 });
				limits = body.providers.gemini.rate_limits;
			}
			return Response.json(response());
		},
		loadAvailableModels: () => {}, requestConfirmation: () => {}, describeApiError: () => 'failed'
	});
	await administration.loadModelSettings();
	const edited = { rpm: 12, tpm: 8000, rpd: 2000 };
	assert.equal(await administration.saveModelProvider('gemini', { rate_limits: edited }), true);
	assert.deepEqual(saved[0], edited);
	assert.deepEqual(administration.modelSettings?.providers.gemini.rate_limits, edited);
	refuse = true;
	assert.equal(await administration.saveModelProvider('gemini', { rate_limits: { rpm: 0, tpm: 0, rpd: 0 } }), false);
	assert.deepEqual(administration.modelSettings?.providers.gemini.rate_limits, edited);
});
