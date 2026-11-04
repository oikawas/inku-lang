import assert from 'node:assert/strict';
import { test } from 'node:test';

const identity = <T>(value: T): T => value;
const stateShim = identity as (<T>(value: T) => T) & { raw: <T>(value: T) => T };
stateShim.raw = identity;
(globalThis as unknown as Record<string, unknown>).$state = stateShim;

const {
	DEFAULT_ANIMATION_EXPORT_SETTINGS,
	animationWarnings,
	animationExportRequest,
	parseAnimationExportSettings,
	loadLastAnimationExport,
	saveLastAnimationExport
} = await import('./animationExport.ts');

test('legacy settings gain layer defaults and requests keep the single-work boundary', () => {
	const settings = parseAnimationExportSettings(JSON.stringify({
		format: 'gif',
		pattern: 'slide',
		holdSeconds: 2,
		resolution: 'custom',
		customHeight: 960
	}));
	assert.equal(settings.showDdl, DEFAULT_ANIMATION_EXPORT_SETTINGS.showDdl);
	assert.equal(settings.layerIntervalSeconds, DEFAULT_ANIMATION_EXPORT_SETTINGS.layerIntervalSeconds);
	assert.equal(settings.layerReplay, DEFAULT_ANIMATION_EXPORT_SETTINGS.layerReplay);

	assert.deepEqual(animationExportRequest(['one', 'one'], settings), {
		ids: ['one'],
		format: 'gif',
		resolution: '1k',
		height_px: 960,
		show_ddl: true,
		replay: 'restart',
		hold_seconds: 0.3
	});
	assert.deepEqual(animationExportRequest(['one', 'two'], settings), {
		ids: ['one', 'two'],
		format: 'gif',
		resolution: '1k',
		height_px: 960,
		pattern: 'slide',
		hold_seconds: 2
	});
	assert.equal(animationExportRequest(['one'], { ...settings, showDdl: false }).show_ddl, false);
});

test('last animation choices survive reload separately for each user', () => {
	const previous = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
	const entries = new Map<string, string>();
	Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
		getItem: (key: string) => entries.get(key) ?? null,
		setItem: (key: string, value: string) => entries.set(key, value),
	} });
	try {
		const a = { ...DEFAULT_ANIMATION_EXPORT_SETTINGS, format: 'gif' as const, showDdl: false, layerReplay: 'once' as const };
		const b = { ...DEFAULT_ANIMATION_EXPORT_SETTINGS, pattern: 'slide' as const, resolution: 'custom' as const, customHeight: 900 };
		assert.equal(loadLastAnimationExport('a'), null);
		saveLastAnimationExport('a', a);
		saveLastAnimationExport('b', b);
		assert.deepEqual(loadLastAnimationExport('a'), a);
		assert.deepEqual(loadLastAnimationExport('b'), b);
		assert.equal(loadLastAnimationExport('c'), null);
		Object.defineProperty(globalThis, 'localStorage', { configurable: true, get: () => { throw new Error('denied'); } });
		assert.equal(loadLastAnimationExport('a'), null);
		assert.doesNotThrow(() => saveLastAnimationExport('a', b));
	} finally {
		if (previous) Object.defineProperty(globalThis, 'localStorage', previous);
		else Reflect.deleteProperty(globalThis, 'localStorage');
	}
});

test('saved-picture mismatch and incomplete compilation are reported independently', () => {
	assert.deepEqual(animationWarnings({ kind: 'folder', folderName: 'test', animationMatchesSaved: 'false', animationCompileOutcome: 'complete' }), { mismatch: true, incomplete: false });
	assert.deepEqual(animationWarnings({ kind: 'folder', folderName: 'test', animationMatchesSaved: 'true', animationCompileOutcome: 'complete_with_omissions' }), { mismatch: false, incomplete: true });
	assert.deepEqual(animationWarnings(null), { mismatch: false, incomplete: false });
});
