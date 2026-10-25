import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { test } from 'node:test';

import type { WorkStateDeps } from '../work/state.svelte.ts';

const libRoot = new URL('../../', import.meta.url);
registerHooks({
	resolve(specifier, context, nextResolve) {
		if (specifier.startsWith('$lib/')) {
			const file = new URL(`${specifier.slice(5)}.ts`, libRoot);
			const target = existsSync(file) ? file : new URL(`${specifier.slice(5)}/index.ts`, libRoot);
			return nextResolve(target.href, context);
		}
		return nextResolve(specifier, context);
	}
});
const identity = <T>(value: T): T => value;
const runeHost = globalThis as unknown as Record<string, unknown>;
runeHost.$state = Object.assign(identity, { raw: identity });
runeHost.$derived = Object.assign(identity, { by: <T>(read: () => T): T => read() });

const notice = await import('./upload-notice.ts');
const { createWorkState } = await import('../work/state.svelte.ts');
const { t } = await import('../../i18n/index.svelte.ts');

function memoryStore() {
	const items = new Map<string, string>();
	return {
		getItem: (key: string) => items.get(key) ?? null,
		setItem: (key: string, value: string) => { items.set(key, value); },
		removeItem: (key: string) => { items.delete(key); },
	};
}

type Confirmation = Parameters<WorkStateDeps['requestConfirmation']>[0];

function pictureWork(due: boolean) {
	const asked: Confirmation[] = [];
	let acknowledged = 0;
	const work = createWorkState({
		apiFetch: async () => { throw new Error('no request expected'); },
		batch: { resuming: false, running: false }, demo: { running: false, updateLiveTime: () => {} },
		refinementSession: { gridBusy: false }, session: {},
		describeApiError: (detail: unknown) => String(detail),
		history: () => ({ clearSelection: () => {} }),
		canvasViewport: { fit: () => {} }, canvasAspectId: () => 'square',
		resetTargetScopedState: () => {}, showCanvas: () => {},
		models: { stage1Provider: () => 'openai', stage1Model: () => 'm', stage2Provider: () => 'openai',
			stage2Model: () => 'm', visionProvider: () => 'openai', visionModel: () => 'v',
			includeThinking: () => false, available: () => [] },
		requestConfirmation: (confirmation: Confirmation) => { asked.push(confirmation); },
		imageUploadNotice: { due: () => due, acknowledge: () => { acknowledged += 1; } },
	} as unknown as WorkStateDeps);
	return { work, asked, acknowledgedCount: () => acknowledged };
}

test('the switch is on until the Server says otherwise', () => {
	assert.equal(notice.imageUploadNoticeEnabled(undefined), true);
	assert.equal(notice.imageUploadNoticeEnabled({ enabled: 'no' }), true);
	assert.equal(notice.imageUploadNoticeEnabled({ enabled: false }), false);
});

test('going on past the warning keeps it quiet until the next sign-in, per account', () => {
	const store = memoryStore();
	notice.applyImageUploadNotice({ enabled: true });
	assert.equal(notice.uploadNoticeDue('a', store), true);
	notice.acknowledgeUploadNotice('a', store);
	assert.equal(notice.uploadNoticeDue('a', store), false);
	assert.equal(notice.uploadNoticeDue('b', store), true);
	notice.forgetUploadNotice('a', store);
	assert.equal(notice.uploadNoticeDue('a', store), true);
});

test('an administrator turning it off silences it for everyone', () => {
	const store = memoryStore();
	notice.applyImageUploadNotice({ enabled: false });
	assert.equal(notice.uploadNoticeDue('a', store), false);
	notice.applyImageUploadNotice({ enabled: true });
	assert.equal(notice.uploadNoticeDue('a', store), true);
});

test('a broken store errs toward warning', () => {
	const broken = { getItem: () => { throw new Error('blocked'); }, setItem: () => { throw new Error('blocked'); }, removeItem: () => {} };
	notice.applyImageUploadNotice({ enabled: true });
	assert.equal(notice.uploadNoticeDue('a', broken), true);
	notice.acknowledgeUploadNotice('a', broken);
});

for (const [name, start] of [
	['the Image tab', (work: ReturnType<typeof pictureWork>['work']) => work.requestSubmitImage()],
	['the picture folder batch', (work: ReturnType<typeof pictureWork>['work']) => work.runImageFolder(true)],
] as const) {
	test(`${name} asks first when the warning is due, and only going on acknowledges it`, () => {
		const { work, asked, acknowledgedCount } = pictureWork(true);
		start(work);
		assert.equal(asked.length, 1);
		assert.equal(asked[0].message, t().imageUploadNoticeMessage);
		assert.equal(acknowledgedCount(), 0);
		asked[0].run();
		assert.equal(acknowledgedCount(), 1);
	});

	test(`${name} does not ask when the warning is not due`, () => {
		const { work, asked } = pictureWork(false);
		start(work);
		assert.equal(asked.length, 0);
	});
}

test('the warning text is the author\'s, word for word', () => {
	const ja = readFileSync(new URL('../../i18n/ja.ts', import.meta.url), 'utf8');
	assert.ok(ja.includes("imageUploadNoticeMessage: '画像から描画を行う場合、画像データがAIにアップロードされます。アップロードされたデータの扱いは、ユーザーが指定したモデルと、それをホストするプロバイダの規約に準じます。\\nセンシティブなデータをアップロードしないでください。'"));
});

test('a sign-in clears the mark, and the page reads the switch from the client config', () => {
	const page = readFileSync(new URL('../../../routes/+page.svelte', import.meta.url), 'utf8');
	assert.match(page, /if \(source === 'login' && session\.currentUser\) forgetUploadNotice\(/);
	assert.match(page, /applyImageUploadNotice\(data\.image_upload_notice\)/);
});
