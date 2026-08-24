import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const WEB = fileURLToPath(new URL('../../', import.meta.url));

test('I-241  the vocabulary lint reads both English Saijiki preview fields', () => {
	const root = mkdtempSync(join(tmpdir(), 'inku-i241-'));
	try {
		mkdirSync(join(root, 'scripts'), { recursive: true });
		mkdirSync(join(root, 'src/lib/i18n'), { recursive: true });
		mkdirSync(join(root, 'src/routes'), { recursive: true });
		copyFileSync(join(WEB, 'scripts/i18n-lint.mjs'), join(root, 'scripts/i18n-lint.mjs'));
		copyFileSync(join(WEB, 'src/lib/i18n/en.ts'), join(root, 'src/lib/i18n/en.ts'));
		copyFileSync(join(WEB, 'src/lib/i18n/ja.ts'), join(root, 'src/lib/i18n/ja.ts'));
		writeFileSync(
			join(root, 'src/routes/+page.svelte'),
			"const previews = { bad: { effectEn: 'An artwork.', exampleEn: 'A magic image.' } };\n"
		);

		const run = spawnSync(process.execPath, ['scripts/i18n-lint.mjs'], {
			cwd: root,
			encoding: 'utf8',
		});
		const output = `${run.stdout ?? ''}${run.stderr ?? ''}`;

		assert.equal(run.status, 1, output);
		assert.match(output, /routes\/\+page\.svelte:1 effectEn: "artwork"/);
		assert.match(output, /routes\/\+page\.svelte:1 exampleEn: "magic"/);
		assert.match(output, /routes\/\+page\.svelte:1 exampleEn: "image"/);
	} finally {
		rmSync(root, { recursive: true, force: true });
	}
});
