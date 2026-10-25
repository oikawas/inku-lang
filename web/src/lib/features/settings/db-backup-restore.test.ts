import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { compileModule } from 'svelte/compiler';
import ts from 'typescript';
import { ja } from '../../i18n/ja';

// Execute the actual Settings owner with the i18n and meter modules stubbed.
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

const entry = { kind: 'manual', name: 'inku-manual-20261025-170000.db', at: Date.UTC(2026, 9, 25, 8), size_bytes: 1, generation: null };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });

function owner() {
	const calls: { path: string; method?: string }[] = [];
	const asked: { message: string; runLabel?: string; destructive?: boolean; run: () => void }[] = [];
	let reloaded = 0;
	const admin = createServerAdministration({
		currentUser: () => ({ id: 'admin', permission_groups: ['admins'] }), setRenderFanoutLimit() {},
		describeApiError: (detail: unknown) => String(detail),
		requestConfirmation: (confirmation: any) => { asked.push(confirmation); },
		reloadPage: () => { reloaded++; },
		apiFetch: async (path: string, init?: RequestInit) => {
			calls.push({ path, method: init?.method });
			if (path.endsWith('/restore')) return json({ restored: entry.name, kind: 'manual', safety_backup: 'inku-manual-20261025-171500.db' });
			return json({ backups: [] });
		}
	});
	return { admin, calls, asked, reloaded: () => reloaded };
}

test('a restore asks twice before it sends, then offers the reload', async () => {
	const { admin, calls, asked, reloaded } = owner();
	admin.restoreDbBackup(entry);
	assert.equal(asked.length, 1);
	assert.equal(asked[0].destructive, true);
	assert.equal(asked[0].runLabel, ja.settingsDbBackupRestoreNext);
	assert.match(asked[0].message, /手動のバックアップとして保存/);
	assert.equal(calls.length, 0, 'the first dialog sends nothing');
	asked[0].run();
	assert.equal(asked.length, 2);
	assert.equal(asked[1].runLabel, ja.settingsDbBackupRestore);
	assert.equal(calls.length, 0, 'the second dialog has not been answered yet');
	asked[1].run();
	await new Promise((resolve) => setTimeout(resolve, 0));
	assert.deepEqual(calls, [{ path: '/api/settings/db-backup/manual/inku-manual-20261025-170000.db/restore', method: 'POST' }]);
	assert.equal(asked.length, 3);
	assert.match(asked[2].message, /inku-manual-20261025-171500\.db/);
	asked[2].run();
	assert.equal(reloaded(), 1);
});

test('a delete asks once and a dismissed dialog sends nothing', async () => {
	const { admin, calls, asked } = owner();
	admin.deleteDbBackup(entry);
	admin.restoreDbBackup(entry);
	assert.equal(asked.length, 2);
	assert.equal(calls.length, 0);
	asked[0].run();
	await new Promise((resolve) => setTimeout(resolve, 0));
	assert.deepEqual(calls, [{ path: '/api/settings/db-backup/manual/inku-manual-20261025-170000.db', method: 'DELETE' }]);
	assert.equal(admin.dbBackupStatus, ja.settingsDbBackupDeleted);
});
