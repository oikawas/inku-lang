import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { pluginProblemMessage } from './plugin-package-problems';

const here = new URL('.', import.meta.url);
const read = (path: string) => readFileSync(new URL(path, here), 'utf8');

test('every problem the Server writes for a package file is explained in both languages', () => {
	const server = read('../../../../../server/src/inku_server/plugins/packages.py');
	const router = read('../../../../../server/src/inku_server/api_core/routers/plugins.py');
	// Problem(path, "code", ...) and, in the zip reader, problem("code", ...).
	const codes = new Set(
		[...`${server}\n${router}`.matchAll(/(?:Problem\([^)]*?,\s*|\bproblem\()"([a-z0-9_]+)"/g)].map((match) => match[1])
	);
	assert.ok(codes.size >= 25, `found only ${codes.size} codes; the pattern no longer reads packages.py`);
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
