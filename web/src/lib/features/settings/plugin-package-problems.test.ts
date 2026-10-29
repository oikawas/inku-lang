import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { pluginProblemMessage, pluginRejectionMessage } from './plugin-package-problems';

const here = new URL('.', import.meta.url);
const read = (path: string) => readFileSync(new URL(path, here), 'utf8');

test('every problem the Server writes for a package file is explained in both languages', () => {
	const server = read('../../../../../server/src/inku_server/plugins/packages.py');
	const router = read('../../../../../server/src/inku_server/api_core/routers/plugins.py');
	const core = read('../../../../../core/crates/inku-pipeline-uniffi/src/plugin_package.rs');
	const definitions = read('../../../../../core/crates/inku-ddl/src/macro_definition.rs');
	// The package shape and ZIP problems now come from the shared core. Server adds
	// file-management and HTTP transport problems at its own boundary.
	const codes = new Set([
		...[...core.matchAll(/\bproblem\(\s*[^,]*,\s*"([a-z0-9_]+)"/g)].map((match) => match[1]),
		...[...core.matchAll(/\berr\(\s*"([a-z0-9_]+)"/g)].map((match) => match[1]),
		...[...definitions.matchAll(/\bpush_diagnostic\(\s*[^,]+,\s*"([a-z0-9_]+)"/g)].map((match) => match[1]),
		...[...`${server}\n${router}`.matchAll(/\bProblem\(\s*"[^"]*",\s*"([a-z0-9_]+)"/g)].map((match) => match[1])
	]);
	assert.ok(codes.size >= 65, `found only ${codes.size} codes; the source patterns need updating`);
	for (const zipCode of ['invalid_zip', 'archive_without_package_json', 'not_base64', 'preview_needs_zip']) {
		assert.ok(codes.has(zipCode), `the pattern missed ${zipCode}`);
	}
	for (const code of codes) {
		assert.notEqual(pluginProblemMessage(code, true), code, `no Japanese explanation for ${code}`);
		assert.notEqual(pluginProblemMessage(code, false), code, `no English explanation for ${code}`);
	}
});

test('a code the table does not know is shown as itself, not hidden', () => {
	assert.equal(pluginProblemMessage('a_code_from_a_newer_core', true), 'a_code_from_a_newer_core');
});

test('rejected installed files show translated check reasons and no drawing hint', () => {
	assert.deepEqual(pluginRejectionMessage('schema: rewrite_as_v2', true), {
		message: '古い形式（v1）のファイルです。inku.plugin-package.v2 に書き直して入れ直してください。', path: 'schema'
	});
	assert.match(pluginRejectionMessage('schema: rewrite_as_v2', false).message, /old v1 format.*inku\.plugin-package\.v2/);
	assert.deepEqual(pluginRejectionMessage('words[0]: unknown_field', false), { message: pluginProblemMessage('unknown_field', false), path: 'words[0]' });
	assert.deepEqual(pluginRejectionMessage('schema: future_code', true), { message: 'future_code', path: 'schema' });
	const settings = read('./PluginAdministrationSettings.svelte');
	assert.match(settings, /plugin\.status === 'rejected'[\s\S]*?settingsPluginNotLoaded[\s\S]*?\{:else\}[\s\S]*?settingsPluginDrawn/);
	assert.match(settings, /plugin\.status !== 'rejected'\}<div class="plugin-use-hint">\{t\(\)\.settingsPluginPackageHint\}/);
	assert.match(settings, /plugin\.kind === 'package' && plugin\.status !== 'rejected'\}<span class="plugin-use-hint">\{t\(\)\.settingsPluginPackageDeleteHint\}/);
	assert.match(settings, /pluginRejectionMessage\(reason, isJapanese\)/);
});
