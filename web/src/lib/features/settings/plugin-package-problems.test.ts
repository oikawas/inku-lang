import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { pluginProblemMessage } from './plugin-package-problems';

const here = new URL('.', import.meta.url);
const read = (path: string) => readFileSync(new URL(path, here), 'utf8');

test('every problem the Server writes for a package file is explained in both languages', () => {
	const server = read('../../../../../server/src/inku_server/plugins/packages.py');
	const codes = new Set([...server.matchAll(/Problem\([^)]*?,\s*"([a-z_]+)"/g)].map((match) => match[1]));
	assert.ok(codes.size >= 15, `found only ${codes.size} codes; the pattern no longer reads packages.py`);
	for (const code of codes) {
		assert.notEqual(pluginProblemMessage(code, true), code, `no Japanese explanation for ${code}`);
		assert.notEqual(pluginProblemMessage(code, false), code, `no English explanation for ${code}`);
	}
});

test('a code the table does not know is shown as itself, not hidden', () => {
	assert.equal(pluginProblemMessage('a_code_from_a_newer_core', true), 'a_code_from_a_newer_core');
});
