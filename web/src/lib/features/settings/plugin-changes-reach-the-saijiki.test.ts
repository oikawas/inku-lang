import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { compileModule } from 'svelte/compiler';
import ts from 'typescript';

// The Saijiki and the DDL editor read the plugin words once after sign-in. A
// plugin added, switched, deleted or given a picture in the settings has to
// tell the page to read them again, and only when the Server took the change.
const stub = (code: string) => 'data:text/javascript;base64,' + Buffer.from(code).toString('base64');
const i18n = stub(`import { ja } from ${JSON.stringify(new URL('../../i18n/ja.ts', import.meta.url).href)}; export const t = () => ja; export const getLang = () => 'ja';`);
const meter = stub('export function applyMeterSwitches() {}');
const uploadNotice = stub('export function applyImageUploadNotice() {}');
const source = ts.transpileModule(readFileSync(new URL('./server-administration.svelte.ts', import.meta.url), 'utf8'), {
	compilerOptions: { target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.ESNext }
}).outputText
	.replace(/(['"])\$lib\/i18n\/index\.svelte\1/g, JSON.stringify(i18n))
	.replace(/(['"])\$lib\/descriptionMeter\.svelte\1/g, JSON.stringify(meter))
	.replace(/(['"])\$lib\/features\/image-provenance\/upload-notice\1/g, JSON.stringify(uploadNotice));
const generated = compileModule(source, { filename: 'server-administration.svelte.js', generate: 'client' }).js.code
	.replace(/(['"])svelte\/internal\/client\1/g, JSON.stringify(import.meta.resolve('svelte/internal/client')));
const { createServerAdministration } = await import(stub(generated));

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });

function owner(status: number) {
	let changed = 0;
	const admin = createServerAdministration({
		currentUser: () => ({ id: 'admin', permission_groups: ['admins'] }), setRenderFanoutLimit() {},
		describeApiError: (detail: unknown) => String(detail),
		requestConfirmation() {},
		pluginsChanged: () => { changed++; },
		apiFetch: async (path: string) => (path === '/api/settings/status' ? json({ plugins: { loaded: [] } }) : json({ detail: 'no' }, status))
	});
	return { admin, changed: () => changed };
}

test('every plugin change the Server took tells the page to read the words again', async () => {
	const { admin, changed } = owner(200);
	assert.equal(await admin.installPluginPackage('{}', false), true);
	assert.equal(await admin.setPluginEnabled('Sky.night', false), true);
	assert.equal(await admin.setPluginWordPicture('Sky.night', 'Stars', null), true);
	assert.equal(await admin.deletePlugin('Sky.night'), true);
	assert.equal(changed(), 4);
});

test('a refused change and a check alone leave the words as they are', async () => {
	const { admin, changed } = owner(403);
	await admin.installPluginPackage('{}', false);
	await admin.setPluginEnabled('Sky.night', false);
	await admin.deletePlugin('Sky.night');
	await owner(200).admin.checkPluginPackage('{}');
	assert.equal(changed(), 0);
});
