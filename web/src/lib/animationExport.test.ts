import assert from 'node:assert/strict';
import { test } from 'node:test';

const identity = <T>(value: T): T => value;
const stateShim = identity as (<T>(value: T) => T) & { raw: <T>(value: T) => T };
stateShim.raw = identity;
(globalThis as unknown as Record<string, unknown>).$state = stateShim;

const {
	DEFAULT_ANIMATION_EXPORT_SETTINGS,
	animationExportRequest,
	parseAnimationExportSettings
} = await import('./animationExport.ts');

test('legacy settings gain layer defaults and requests keep the single-work boundary', () => {
	const settings = parseAnimationExportSettings(JSON.stringify({
		format: 'gif',
		pattern: 'slide',
		holdSeconds: 2,
		resolution: 'custom',
		customHeight: 960
	}));
	assert.equal(settings.layerFrameCount, DEFAULT_ANIMATION_EXPORT_SETTINGS.layerFrameCount);
	assert.equal(settings.layerIntervalSeconds, DEFAULT_ANIMATION_EXPORT_SETTINGS.layerIntervalSeconds);
	assert.equal(settings.layerReplay, DEFAULT_ANIMATION_EXPORT_SETTINGS.layerReplay);

	assert.deepEqual(animationExportRequest(['one', 'one'], settings), {
		ids: ['one'],
		format: 'gif',
		resolution: '1k',
		height_px: 960,
		layer_frame_count: 12,
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
});
