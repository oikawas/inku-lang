import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { compileModule } from 'svelte/compiler';
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
