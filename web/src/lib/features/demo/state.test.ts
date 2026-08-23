import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { test } from 'node:test';

import type { CurrentWorkResult } from '../run/current-work.ts';

const identity = <T>(value: T): T => value;
const stateShim = identity as (<T>(value: T) => T) & { raw: <T>(value: T) => T };
stateShim.raw = identity;
const runeHost = globalThis as unknown as Record<string, unknown>;
runeHost.$state = stateShim;
runeHost.$derived = identity;

// The app's demo schema uses Vite's $lib alias. Keep this direct Node test
// local: production imports and the canonical defaults remain unchanged.
registerHooks({
	resolve(specifier, context, nextResolve) {
		if (specifier === '$lib/models') {
			return nextResolve(new URL('../../models.ts', import.meta.url).href, context);
		}
		return nextResolve(specifier, context);
	},
});

const { DemoState } = await import('./state.svelte.ts');

function paintedResult(): CurrentWorkResult {
	return {
		ddl: 'circle 10',
		thinking: null,
		svg: '<svg/>',
		score: { instructions: [] },
		elapsed_stage1_ms: 20,
		elapsed_stage2_ms: 30,
		elapsed_total_ms: 50,
		tokens_in_stage1: 2,
		tokens_out_stage1: 3,
		tokens_in_stage2: 5,
		tokens_out_stage2: 7,
	};
}

function jsonResponse(value: unknown, status = 200): Response {
	return new Response(JSON.stringify(value), {
		status,
		headers: { 'Content-Type': 'application/json' },
	});
}

function runOptions(overrides: Partial<Parameters<InstanceType<typeof DemoState>['start']>[0]> = {}) {
	return {
		canvasAspectId: () => 'square' as const,
		renderOverrides: () => ({ catalog_id: 'seasonal', wild: false }),
		paintInstruction: async () => paintedResult(),
		onLatestResult: () => {},
		onRunFinished: () => {},
		refreshAfterServerSave: async () => {},
		refreshAfterRun: async () => {},
		...overrides,
	};
}

test('T-902: settings preserve legacy normalization, persistence, and catalog fallback', async () => {
	const requests: Array<{ path: string; init?: RequestInit }> = [];
	const state = new DemoState({
		apiFetch: async (path, init) => {
			requests.push({ path, init });
			if (!init?.method) return jsonResponse({
				...state.settings,
				prompt_provider: 'ignored',
				prompt_model: 'openai:legacy-model',
				seed_phrase: '   ',
				interval_seconds: 0,
				timeout_seconds: 0,
			});
			return jsonResponse(JSON.parse(String(init.body)));
		},
		signedIn: () => true,
		instructionLang: () => 'auto',
		uiLang: () => 'ja',
		describeApiError: (_detail, status) => `HTTP ${status}`,
	});

	await state.loadSettings();
	assert.equal(state.settingsLoaded, true);
	assert.equal(state.settings.prompt_provider, 'openai');
	assert.equal(state.settings.prompt_model, 'legacy-model');
	assert.equal(state.settings.interval_seconds, 30);
	assert.equal(state.settings.timeout_seconds, 3600);
	assert.ok(state.settings.seed_phrase.length > 0);

	await state.saveSettings({
		...state.settings,
		seed_phrase: '  next seed  ',
		interval_seconds: 99_999,
		timeout_seconds: 1,
	});
	const saved = JSON.parse(String(requests.at(-1)?.init?.body));
	assert.equal(saved.seed_phrase, 'next seed');
	assert.equal(saved.interval_seconds, 3600);
	assert.equal(saved.timeout_seconds, 60);

	state.settings = { ...state.settings, prompt_provider: 'missing', prompt_model: 'gone' };
	state.reconcilePromptModel([
		{ id: 'empty', label: 'Empty', models: [] },
		{ id: 'fallback', label: 'Fallback', models: [{ id: 'first', label: 'First' }] },
	], true);
	assert.equal(state.settings.prompt_provider, 'fallback');
	assert.equal(state.settings.prompt_model, 'first');

	const signedOutRequests = requests.length;
	state.resetForSignedOut();
	assert.equal(state.settingsLoaded, false);
	assert.equal(requests.length, signedOutRequests);
});

test('T-903: one run repeats in order with paint semantics, totals, refresh, and interval waits', async () => {
	let now = 0;
	let instructionNumber = 0;
	const paintOptions: Array<{ prompt: string; options: Parameters<Parameters<InstanceType<typeof DemoState>['start']>[0]['paintInstruction']>[1] }> = [];
	const adopted: string[] = [];
	const sleeps: number[] = [];
	let savedRefreshes = 0;
	let runRefreshes = 0;
	const state = new DemoState({
		apiFetch: async (path) => {
			assert.equal(path, '/api/demo/instruction');
			instructionNumber += 1;
			return jsonResponse({ instruction: `prompt-${instructionNumber}` });
		},
		signedIn: () => false,
		instructionLang: () => 'en',
		uiLang: () => 'en',
		describeApiError: (_detail, status) => `HTTP ${status}`,
		now: () => now,
		sleep: async (ms) => { sleeps.push(ms); now += ms; },
	});
	state.settings = { ...state.settings, save_db: true, save_files: true, interval_seconds: 1, timeout_seconds: 60 };

	await state.start(runOptions({
		paintInstruction: async (prompt, options) => {
			paintOptions.push({ prompt, options });
			return { ...paintedResult(), ddl: `ddl-${paintOptions.length}` };
		},
		onLatestResult: (result, prompt) => { adopted.push(`${prompt}:${result.ddl}`); },
		refreshAfterServerSave: async () => {
			savedRefreshes += 1;
			if (savedRefreshes === 3) state.stop();
		},
		refreshAfterRun: async () => { runRefreshes += 1; },
	}));

	assert.deepEqual(adopted, ['prompt-1:ddl-1', 'prompt-2:ddl-2', 'prompt-3:ddl-3']);
	assert.equal(paintOptions[0]?.options.saveHistory, true);
	assert.equal(paintOptions[0]?.options.saveArtifacts, true);
	assert.equal(paintOptions[0]?.options.countGeneration, false);
	assert.equal(paintOptions[0]?.options.historyInput, '[demo] prompt-1');
	assert.equal(paintOptions[0]?.options.sourceText, 'prompt-1');
	assert.equal(paintOptions[0]?.options.displayLabel, '[demo]');
	assert.equal(paintOptions[0]?.options.canvasAspectId, 'square');
	assert.deepEqual(paintOptions[0]?.options.renderOverrides, { catalog_id: 'seasonal', wild: false });
	assert.deepEqual(sleeps, [1000, 1000]);
	assert.equal(state.totalElapsedMs, 150);
	assert.equal(state.totalTokensIn, 21);
	assert.equal(state.totalTokensOut, 30);
	assert.equal(state.renderCount, 3);
	assert.equal(state.latestResult?.ddl, 'ddl-3');
	assert.equal(savedRefreshes, 3);
	assert.equal(runRefreshes, 1);
});

test('T-904: timeout finishes once and records the timed-out projection', async () => {
	let now = 0;
	let finished = 0;
	let refreshed = 0;
	const state = new DemoState({
		apiFetch: async () => jsonResponse({ instruction: 'one prompt' }),
		signedIn: () => false,
		instructionLang: () => 'auto',
		uiLang: () => 'ja',
		describeApiError: (_detail, status) => `HTTP ${status}`,
		now: () => now,
		sleep: async (ms) => { now += ms; },
	});
	state.settings = { ...state.settings, interval_seconds: 60, timeout_seconds: 60 };

	await state.start(runOptions({
		onRunFinished: () => { finished += 1; },
		refreshAfterRun: async () => { refreshed += 1; },
	}));

	assert.equal(state.timedOut, true);
	assert.equal(state.running, false);
	assert.equal(state.waitingSeconds, null);
	assert.equal(finished, 1);
	assert.equal(refreshed, 1);
});

test('T-905: stop rejects an instruction that resolves after its run ended', async () => {
	let resolveInstruction!: (response: Response) => void;
	const instruction = new Promise<Response>((resolve) => { resolveInstruction = resolve; });
	let paintCalls = 0;
	let canvasCalls = 0;
	let refreshCalls = 0;
	const state = new DemoState({
		apiFetch: async (path) => {
			if (path === '/api/demo/instruction') return instruction;
			return new Response('{}', { status: 200 });
		},
		signedIn: () => false,
		instructionLang: () => 'en',
		uiLang: () => 'en',
		describeApiError: (_detail, status) => `HTTP ${status}`,
	});

	const running = state.start(runOptions({
		paintInstruction: async () => {
			paintCalls += 1;
			return paintedResult();
		},
		onLatestResult: () => { canvasCalls += 1; },
		refreshAfterRun: async () => { refreshCalls += 1; },
	}));
	await Promise.resolve();

	state.stop();
	resolveInstruction(new Response(JSON.stringify({ instruction: 'late prompt' }), {
		status: 200,
		headers: { 'Content-Type': 'application/json' },
	}));
	await running;

	assert.equal(state.generatedPrompt, '');
	assert.equal(state.latestResult, null);
	assert.equal(state.renderCount, 0);
	assert.equal(paintCalls, 0);
	assert.equal(canvasCalls, 0);
	assert.equal(state.timedOut, false);
	assert.equal(state.currentLiveMs, null);
	assert.equal(state.waitingSeconds, null);
	assert.equal(refreshCalls, 1);
});

test('T-905: stop rejects a paint result that resolves after its run ended', async () => {
	let resolvePaint!: (result: CurrentWorkResult) => void;
	const pendingPaint = new Promise<CurrentWorkResult>((resolve) => { resolvePaint = resolve; });
	let canvasCalls = 0;
	const state = new DemoState({
		apiFetch: async () => jsonResponse({ instruction: 'ready prompt' }),
		signedIn: () => false,
		instructionLang: () => 'en',
		uiLang: () => 'en',
		describeApiError: (_detail, status) => `HTTP ${status}`,
	});

	const running = state.start(runOptions({
		paintInstruction: async () => pendingPaint,
		onLatestResult: () => { canvasCalls += 1; },
	}));
	await Promise.resolve();
	await Promise.resolve();
	state.stop();
	resolvePaint(paintedResult());
	await running;

	assert.equal(state.generatedDdl, null);
	assert.equal(state.latestResult, null);
	assert.equal(state.totalElapsedMs, 0);
	assert.equal(state.totalTokensIn, 0);
	assert.equal(state.totalTokensOut, 0);
	assert.equal(state.renderCount, 0);
	assert.equal(canvasCalls, 0);
});

test('T-906: manual save preserves payload meaning and updates the current projection after success', async () => {
	let request: { path: string; init?: RequestInit } | null = null;
	let projected: CurrentWorkResult | null = null;
	let refreshed = 0;
	const state = new DemoState({
		apiFetch: async (path, init) => {
			request = { path, init };
			return jsonResponse({ id: 'saved-id', at: 1234, render_hash: 'hash', render_hash_short: 'short' });
		},
		signedIn: () => true,
		instructionLang: () => 'auto',
		uiLang: () => 'ja',
		describeApiError: (_detail, status) => `HTTP ${status}`,
		now: () => 999,
	});
	state.settings = { ...state.settings, save_files: true };
	state.generatedPrompt = 'current prompt';
	state.generatedDdl = 'current ddl';
	state.latestResult = {
		...paintedResult(),
		sketch_text: 'sketch prose',
		sketch_grain: 'fine',
		sketch_state: 'generated',
		compose_fallback_used: true,
		compose_retry_reasons: ['stage2_hard_timeout'],
	};

	await state.saveCurrent({
		stage1Model: 'openai:stage-1',
		stage2Model: 'openai:stage-2',
		effectiveCatalogId: 'seasonal',
		canvasAspectId: 'portrait',
		instructionLang: 'auto',
		uiLang: 'ja',
		savedStatus: 'saved',
		onSaved: (result) => { projected = result; },
		refreshHistory: async () => { refreshed += 1; },
	});

	assert.equal(request?.path, '/api/history');
	const payload = JSON.parse(String(request?.init?.body));
	assert.deepEqual({
		input: payload.input,
		source_text: payload.source_text,
		display_label: payload.display_label,
		ddl: payload.ddl,
		at: payload.at,
		stage1_model: payload.stage1_model,
		stage2_model: payload.stage2_model,
		tokens_in: payload.tokens_in,
		tokens_out: payload.tokens_out,
		catalog_id: payload.catalog_id,
		save_artifacts: payload.save_artifacts,
		canvas_aspect: payload.canvas_aspect,
		instruction_lang_requested: payload.instruction_lang_requested,
		ui_lang: payload.ui_lang,
		sketch_text: payload.sketch_text,
		sketch_grain: payload.sketch_grain,
		sketch_state: payload.sketch_state,
		compose_fallback: payload.compose_fallback,
	}, {
		input: '[demo] current prompt',
		source_text: 'current prompt',
		display_label: '[demo]',
		ddl: 'current ddl',
		at: 999,
		stage1_model: 'openai:stage-1',
		stage2_model: 'openai:stage-2',
		tokens_in: 7,
		tokens_out: 10,
		catalog_id: 'seasonal',
		save_artifacts: true,
		canvas_aspect: 'portrait',
		instruction_lang_requested: 'auto',
		ui_lang: 'ja',
		sketch_text: 'sketch prose',
		sketch_grain: 'fine',
		sketch_state: 'generated',
		compose_fallback: 'stage2_hard_timeout',
	});
	assert.equal(state.currentSaved, true);
	assert.equal(state.saveStatus, 'saved');
	assert.equal(state.latestResult?.history_id, 'saved-id');
	assert.equal(projected?.history_id, 'saved-id');
	assert.equal(refreshed, 1);
});
