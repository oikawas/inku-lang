import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ja } from '../../i18n/ja.ts';
import { en } from '../../i18n/en.ts';
import type { BatchFailureReport } from './failure-report.svelte.ts';

const identity = <T>(value: T): T => value;
const stateShim = identity as (<T>(value: T) => T) & { raw: <T>(value: T) => T };
stateShim.raw = identity;
const runeHost = globalThis as unknown as Record<string, unknown>;
runeHost.$state = stateShim;
runeHost.$derived = identity;

const { BatchState } = await import('./state.svelte.ts');
const { ConnectionFailure } = await import('../../transport/connection-failure.ts');

type PendingResult = {
	resolve: (value: ReturnType<typeof result>) => void;
};

function result(line: number, tokensIn = line, tokensOut = line * 2) {
	return {
		ddl: `ddl-${line}`,
		thinking: `thinking-${line}`,
		sketch_text: `sketch-${line}`,
		sketch_grain: 'fine',
		tokens_in_stage1: tokensIn,
		tokens_in_stage2: 0,
		tokens_out_stage1: tokensOut,
		tokens_out_stage2: 0,
	};
}

function jsonResponse(value: unknown, status = 200): Response {
	return new Response(JSON.stringify(value), {
		status,
		headers: { 'Content-Type': 'application/json' },
	});
}

function makeState(
	apiFetch: (path: string, init?: RequestInit) => Promise<Response> = async () => jsonResponse({ items: [] }),
	createRunId: () => string = () => 'run-fixed',
	warn?: (message: string, cause: unknown) => void,
) {
	const reports: unknown[] = [];
	const state = new BatchState({
		apiFetch: (path, init) => path.startsWith('/api/pipeline/batches') || path === '/api/pipeline/activity'
			? Promise.resolve(new Response('', { status: 404 })) : apiFetch(path, init),
		signedIn: () => true,
		paintable: (text) => text.trim().length > 0,
		setFailureReport: (report) => reports.push(report),
		createRunId,
		warn,
	});
	return { state, reports };
}

test('each batch work starts its own clock and a cut connection keeps that start', async () => {
	let clock = 100_000, secondSends = 0, probes = 0;
	const state = new BatchState({
		apiFetch: async (path) => path.startsWith('/api/pipeline/batches') || path === '/api/pipeline/activity'
			? new Response('', { status: 404 }) : path === '/api/info' && probes++ === 0
				? new Response('', { status: 503 }) : jsonResponse({ items: [] }),
		signedIn: () => true, paintable: (text) => !!text.trim(), setFailureReport: () => {},
		now: () => clock, sleep: async (ms) => { clock += ms; }, createRunId: () => 'run-clock',
	});
	state.input = 'first\nsecond';
	const starts: Array<number | null> = [];
	await state.run({ canvasAspectId: 'square', maxRetries: 0,
		paintLine: async (_text, options) => {
			starts.push(state.workStartedAt);
			if (options.batchLineNumber === 1) { clock += 10_000; return result(1); }
			if (++secondSends === 1) { clock += 3_000; throw new ConnectionFailure('cut', 'cut'); }
			clock += 4_000;
			return result(2);
		},
		onLatestResult: () => {}, refreshAfterServerSave: async () => {}, refreshAfterRun: async () => {},
	});
	assert.deepEqual(starts, [100_000, 110_000, 110_000]);
	assert.equal(state.averageWorkMs, 9_500);
});

test('batch average uses saved works only and begins empty on each run', async () => {
	let clock = 100_000;
	const state = new BatchState({ apiFetch: async (path) => path.startsWith('/api/pipeline/batches')
		? new Response('', { status: 404 }) : jsonResponse({ items: [] }),
		signedIn: () => true, paintable: (text) => !!text.trim(), setFailureReport: () => {}, now: () => clock });
	state.input = 'first\nfail\nlast';
	await state.run({ canvasAspectId: 'square', maxRetries: 0,
		paintLine: async (text, options) => {
			if (text === 'first') { assert.equal(state.averageWorkMs, null); clock += 10_000; }
			if (text === 'fail') { clock += 100_000; throw new Error('failed'); }
			if (text === 'last') { assert.equal(state.averageWorkMs, 10_000); clock += 30_000; }
			return result(options.batchLineNumber!);
		},
		onLatestResult: () => {}, refreshAfterServerSave: async () => {}, refreshAfterRun: async () => {},
	});
	assert.equal(state.averageWorkMs, 20_000);
	await state.run({ canvasAspectId: 'square', maxRetries: 0,
		paintLine: async () => { assert.equal(state.averageWorkMs, null); state.stop(); return result(1); },
		onLatestResult: () => {}, refreshAfterServerSave: async () => {}, refreshAfterRun: async () => {},
	});
	assert.equal(state.averageWorkMs, null);
});

test('new batch clears the interruption and pending resume together', () => {
	const { state } = makeState();
	state.interrupted = true;
	state.resume = { prompt: 'first', lines: [{ line: 1, input: 'first' }], runId: 'old', work: null,
		conditions: { stage1Model: null, stage2Model: null, catalogId: null, catalogMode: null,
			sketchGrain: null, wild: null, canvasAspectId: null }, pending: null, source: 'history' };
	state.clearInput();
	assert.equal(state.interrupted, false);
	assert.equal(state.resume, null);
});

test('a saved batch work is shown only after its history refresh', async () => {
	const { state } = makeState();
	state.input = 'first';
	const events: string[] = [];
	await state.run({ canvasAspectId: 'square', maxRetries: 0, paintLine: async () => result(1),
		refreshAfterServerSave: async () => { events.push('history'); },
		onLatestResult: () => { events.push('shown'); }, refreshAfterRun: async () => {} });
	assert.deepEqual(events, ['history', 'shown']);
});

test('an expired registered batch can resume even before its first saved work, but an active batch cannot', async () => {
	const record = { run_id: 'recorded-run', kind: 'web', total: 2, completed: 0,
		state: 'running', prompt: 'first\nsecond', conditions: {
			stage1Model: null, stage2Model: null, catalogId: null, catalogMode: null,
			sketchGrain: null, wild: null, canvasAspectId: null,
		}, updated_at: 1 };
	const state = new BatchState({
		apiFetch: async (path) => path === '/api/pipeline/batches'
			? jsonResponse({ batches: [record] }) : jsonResponse({ items: [] }),
		signedIn: () => true, paintable: (text) => !!text.trim(), setFailureReport: () => {},
	});
	await state.refreshResume();
	assert.equal(state.canResume, false);
	record.state = 'uncertain';
	await state.refreshResume();
	assert.equal(state.canResume, false);
	record.state = 'interrupted';
	await state.refreshResume();
	assert.equal(state.canResume, true);
	assert.equal(state.resume?.runId, 'recorded-run');
	assert.deepEqual(state.resume?.lines.map((line) => line.input), ['first', 'second']);
});

test('resume reconciles saved lines and sends only the remaining line with the new lease', async () => {
	const conditions = { stage1Model: null, stage2Model: null, catalogId: null, catalogMode: null,
		sketchGrain: null, wild: null, canvasAspectId: null };
	const record = { run_id: 'run-old', kind: 'web', total: 2, completed: 0, state: 'lease_expired',
		prompt: 'first\nsecond', conditions, updated_at: 1 };
	const calls: Array<{ line: number | undefined; lease: string | undefined }> = [];
	const state = new BatchState({
		apiFetch: async (path, init) => {
			if (path === '/api/pipeline/batches' && init?.method === 'POST') return jsonResponse({ lease: 'new-lease' });
			if (path.startsWith('/api/pipeline/batches/')) return jsonResponse({ ok: true });
			if (path === '/api/pipeline/batches') return jsonResponse({ batches: [record] });
			if (path.startsWith('/api/history')) return jsonResponse({ items: [{ batch_run_id: 'run-old', batch_line_number: 1 }] });
			throw new Error(`unexpected ${path}`);
		},
		signedIn: () => true, paintable: (text) => !!text.trim(), setFailureReport: () => {},
	});
	await state.refreshResume();
	await state.resumeInterrupted({ blocked: () => false, applyConditions: () => {}, run: (lines) => state.run({
		resumeLines: lines, canvasAspectId: 'square', maxRetries: 0,
		paintLine: async (_text, options) => { calls.push({ line: options.batchLineNumber, lease: options.batchLease }); return result(2); },
		onLatestResult: () => {}, refreshAfterServerSave: async () => {}, refreshAfterRun: async () => {},
	}) });
	assert.deepEqual(calls, [{ line: 2, lease: 'new-lease' }]);
});

test('a cut batch waits for its still-running server work before checking history', async () => {
	let checks = 0, paints = 0, clock = 0;
	const state = new BatchState({
		apiFetch: async (path) => {
			if (path.startsWith('/api/pipeline/batches')) return new Response('', { status: 404 });
			if (path === '/api/pipeline/activity') return jsonResponse({ executions: ++checks === 1 ? [{ batch_run_id: 'run-fixed' }] : [] });
			if (path.startsWith('/api/history')) return jsonResponse({ items: [{ batch_run_id: 'run-fixed', batch_line_number: 1, at: 1000 }] });
			return jsonResponse({});
		},
		signedIn: () => true, paintable: (text) => !!text.trim(), setFailureReport: () => {},
		createRunId: () => 'run-fixed', now: () => clock,
		sleep: async (ms) => { clock += ms; },
	});
	state.input = 'first';
	await state.run({ canvasAspectId: 'square', maxRetries: 0,
		paintLine: async () => { paints += 1; throw new ConnectionFailure('unreachable', 'cut'); },
		onLatestResult: () => {}, refreshAfterServerSave: async () => {}, refreshAfterRun: async () => {},
	});
	assert.equal(checks, 2);
	assert.equal(paints, 1);
	assert.equal(state.success, 1);
	assert.equal(state.averageWorkMs, 1000);
});

test('a resumed batch summary uses the original total and counts pending positions', async () => {
	const { state } = makeState();
	state.input = 'first\n\nsecond\nthird';
	const shown: number[] = [];
	await state.run({
		resumeLines: [{ line: 3, input: 'second' }, { line: 4, input: 'third' }],
		canvasAspectId: 'square', maxRetries: 0,
		paintLine: async (_text, options) => {
			assert.equal(state.summaryTotal, 3);
			assert.ok(state.startedAt > 0);
			shown.push(state.summaryCurrent);
			return result(options.batchLineNumber!);
		},
		onLatestResult: () => {}, refreshAfterServerSave: async () => {}, refreshAfterRun: async () => {},
	});
	assert.deepEqual(shown, [2, 3]);
});

test('manual failure retry paints only errors, keeps original conditions and numbering, and removes recovered errors', async () => {
	const { state, reports } = makeState();
	const original = 'saved\n\nfailed\nother failure';
	const conditions = {
		stage1Model: 'provider/original', stage2Model: null, catalogId: 'sumi', catalogMode: 'fixed' as const,
		sketchGrain: 'fine', wild: true, canvasAspectId: 'square',
	};
	state.input = original;
	const calls: Array<{ text: string; line: number; id: string }> = [];
	let manualRound = 0;
	const run = (retryFailedLines?: Array<{ line: number; input: string }>) => state.run({
		retryFailedLines, runConditions: conditions, canvasAspectId: 'square', maxRetries: 0,
		paintLine: async (text, options) => {
			const line = options.batchLineNumber!;
			calls.push({ text, line, id: options.batchRunId! });
			if (line !== 1 && (manualRound === 0 || (line === 4 && manualRound === 1))) throw new Error(`failure-${manualRound}`);
			return result(line);
		},
		onLatestResult: () => {}, refreshAfterServerSave: async () => {}, refreshAfterRun: async () => {},
	});
	await run();
	assert.equal(state.canRetryFailures, true);
	state.input = 'edited input that must not be painted';
	const applied: unknown[] = [];
	const retry = () => state.retryFailed({
		blocked: () => false, applyConditions: (value) => applied.push(value), run,
	});
	manualRound = 1;
	await retry();
	assert.deepEqual(calls.slice(3), [
		{ text: 'failed', line: 3, id: 'run-fixed' }, { text: 'other failure', line: 4, id: 'run-fixed' },
	]);
	assert.equal(state.input, original);
	assert.deepEqual(applied, [conditions]);
	assert.deepEqual(state.failures, [{ line: 4, input: 'other failure', message: 'failure-1' }]);
	assert.equal((reports.at(-1) as { success: number }).success, 2);
	manualRound = 2;
	await retry();
	assert.deepEqual(calls.slice(5), [{ text: 'other failure', line: 4, id: 'run-fixed' }]);
	assert.equal(state.canRetryFailures, false);
	assert.equal(reports.at(-1), null);
});

test('manual failure retry after stop excludes aborted and unattempted lines and preserves errors when stopped again', async () => {
	const { state } = makeState();
	state.input = 'saved\nfailed\nsecond failure\naborted\nunattempted';
	let manual = false;
	let stopRetry = true;
	const calls: number[] = [];
	const run = (retryFailedLines?: Array<{ line: number; input: string }>) => state.run({
		retryFailedLines, canvasAspectId: 'square', maxRetries: 0,
		paintLine: async (_text, options) => {
			const line = options.batchLineNumber!;
			calls.push(line);
			if ((!manual && line === 4) || (manual && stopRetry)) { state.stop(); return result(line); }
			if (!manual && line !== 1) throw new Error('failed');
			return result(line);
		},
		onLatestResult: () => {}, refreshAfterServerSave: async () => {}, refreshAfterRun: async () => {},
	});
	await run();
	manual = true;
	const retry = () => state.retryFailed({ blocked: () => false, applyConditions: () => {}, run });
	await retry();
	assert.deepEqual(calls, [1, 2, 3, 4, 2]);
	assert.deepEqual(state.failures.map((failure) => failure.line), [2, 3]);
	stopRetry = false;
	await retry();
	assert.deepEqual(calls.slice(5), [2, 3]);
	assert.deepEqual(state.resume?.pending?.map((line) => line.line), [4, 5]);
	assert.equal(state.canRetryFailures, false);
});

test('manual failure retry restores full persisted descriptions beyond the display excerpt and ignores the edited box', async () => {
	const full = '長い記述'.repeat(100);
	const conditions = { stage1Model: 'provider/original', stage2Model: null, catalogId: null,
		catalogMode: null, sketchGrain: null, wild: false, canvasAspectId: 'square' };
	let report = { success: 1, total: 2, failures: [{ line: 3, input: full.slice(0, 300), message: 'failed' }],
		retry: { prompt: `saved\n\n${full}`, runId: 'persisted-run', conditions, failedLines: [3], pendingLines: [3] } };
	const state = new BatchState({ apiFetch: async (path) => path.startsWith('/api/pipeline/batches') || path === '/api/pipeline/activity' ? new Response('', { status: 404 }) : jsonResponse({ items: [] }), signedIn: () => true,
		paintable: (text) => text.trim().length > 0,
		getFailureReport: () => report,
		setFailureReport: (value) => { report = value as typeof report; },
	});
	state.input = 'different prompt';
	const calls: unknown[] = [];
	await state.retryFailed({ blocked: () => false, applyConditions: (value) => assert.deepEqual(value, conditions),
		run: (retryFailedLines) => state.run({ retryFailedLines, canvasAspectId: 'square', maxRetries: 0,
			paintLine: async (text, options) => { calls.push([text, options.batchLineNumber, options.batchRunId]); return result(3); },
			onLatestResult: () => {}, refreshAfterServerSave: async () => {}, refreshAfterRun: async () => {},
		}),
	});
	assert.deepEqual(calls, [[full, 3, 'persisted-run']]);
	assert.equal(state.canRetryFailures, false);
});

test('T-802/T-803/T-804: line identity, retry recovery, totals, and latest work stay one run', async () => {
	const { state, reports } = makeState();
	state.input = 'first\n\nthird';
	const attempts = new Map<number, number>();
	const calls: Array<{ text: string; options: Record<string, unknown> }> = [];
	const latest: string[] = [];

	await state.run({
		canvasAspectId: 'square',
		maxRetries: 1,
		paintLine: async (text, options) => {
			const line = options.batchLineNumber!;
			calls.push({ text, options: options as unknown as Record<string, unknown> });
			attempts.set(line, (attempts.get(line) ?? 0) + 1);
			if (line === 3 && attempts.get(line) === 1) throw new Error('temporary');
			return result(line);
		},
		onLatestResult: (_painted, prompt) => latest.push(prompt),
		refreshAfterServerSave: async () => {},
		refreshAfterRun: async () => {},
	});

	assert.deepEqual(calls.map((call) => [call.text, call.options.batchLineNumber]), [
		['first', 1],
		['third', 3],
		['third', 3],
	]);
	assert.equal(calls[2]?.options.historyInput, '#3 third');
	assert.equal(calls[2]?.options.displayLabel, '#3');
	assert.equal(calls[2]?.options.batchRunId, 'run-fixed');
	assert.equal(state.success, 2);
	assert.deepEqual(state.failures, []);
	assert.equal(state.total, 2);
	assert.equal(state.tokensInTotal, 4);
	assert.equal(state.tokensOutTotal, 8);
	assert.equal(state.latestPrompt, '#3 third');
	assert.deepEqual(latest, ['#1 first', '#3 third']);
	assert.ok(reports.some((report) => JSON.stringify(report).includes('temporary')));
	assert.equal(reports.at(-1), null);
});

test('T-804: clearing input preserves the last batch projection for mode changes', () => {
	const { state, reports } = makeState();
	const latest = result(1);
	state.input = 'first';
	state.latestResult = latest;
	state.latestDdl = latest.ddl;
	state.latestThinking = latest.thinking;
	state.latestPrompt = '#1 first';
	state.failures = [{ line: 1, input: 'first', message: 'temporary' }];

	state.clearInput();

	assert.equal(state.input, '');
	assert.deepEqual(state.failures, []);
	assert.equal(state.latestPrompt, '');
	assert.equal(state.latestResult, latest);
	assert.equal(state.latestDdl, latest.ddl);
	assert.equal(state.latestThinking, latest.thinking);
	assert.equal(reports.at(-1), null);
});

test('T-805: cancel owns the signal and rejects a late result from the stopped run', async () => {
	const { state } = makeState();
	state.input = 'first\nsecond';
	let pending: PendingResult | null = null;
	let seenSignal: AbortSignal | null = null;
	let latestCalls = 0;
	const running = state.run({
		canvasAspectId: 'square',
		maxRetries: 3,
		paintLine: async (_text, options) => {
			seenSignal = options.signal ?? null;
			return await new Promise((resolve) => { pending = { resolve }; });
		},
		onLatestResult: () => { latestCalls += 1; },
		refreshAfterServerSave: async () => {},
		refreshAfterRun: async () => {},
	});

	while (!pending) await new Promise((resolve) => setTimeout(resolve, 0));
	state.stop();
	assert.equal(seenSignal?.aborted, true);
	pending?.resolve(result(1));
	await running;

	assert.equal(latestCalls, 0);
	assert.equal(state.success, 0);
	assert.equal(state.tokensInTotal, 0);
	assert.equal(state.latestResult, null);
	assert.equal(state.running, false);
});

test('T-806: prompt history and resume are owned together without renumbering remaining lines', async () => {
	const prompt = 'first\nsecond\nthird';
	const newest = {
		batch_line_number: 2,
		batch_run_id: 'run-old',
		source_text: 'second',
		stage1_model: 'provider/model-1',
		draw_options: { route: 'stages', sketch: 'off', composition: 'off', wild: 'off',
			catalog: null, canvas_aspect: null, models: { stage1: 'provider/model-1' } },
	};
	const requests: Array<{ path: string; init?: RequestInit }> = [];
	const { state } = makeState(async (path, init) => {
		requests.push({ path, init });
		if (path === '/api/auth/me/batch-prompt-history' && !init?.method) {
			return jsonResponse({ items: [` ${prompt} `, prompt, '', 'older'] });
		}
		if (path === '/api/auth/me/batch-prompt-history' && init?.method === 'PUT') {
			return jsonResponse({ items: [prompt, 'older'] });
		}
		if (path.includes('offset=0&limit=20')) return jsonResponse({ items: [newest] });
		if (path.includes('offset=0&limit=100')) {
			return jsonResponse({ items: [newest, { batch_line_number: 1, batch_run_id: 'run-old', source_text: 'first' }] });
		}
		return jsonResponse({ items: [] });
	});

	await state.loadPromptHistory();
	assert.deepEqual(state.promptHistory, [prompt, 'older']);
	await state.refreshResume();
	assert.equal(state.resume?.runId, 'run-old');

	let restored: unknown = null;
	let resumed: unknown = null;
	await state.resumeInterrupted({
		blocked: () => false,
		applyConditions: (conditions) => { restored = conditions; },
		run: async (lines) => { resumed = lines; },
	});

	assert.equal(state.input, prompt);
	assert.equal(state.resume?.source, 'session');
	assert.deepEqual(state.resumeInfo, { nextLine: 3, pending: 1, total: 3 });
	assert.deepEqual(resumed, [{ line: 3, input: 'third' }]);
	assert.equal((restored as { stage1Model?: string }).stage1Model, 'provider/model-1');
	assert.match(requests.at(-1)?.path ?? '', /limit=100/);
});

test('T-808: paused runs retain blank-line numbering, completed saves, conditions, and one id across a second pause', async () => {
	const ids = ['run-original', 'run-should-not-be-used'];
	const { state } = makeState(undefined, () => ids.shift() ?? 'unexpected');
	state.input = 'first\n\nthird\nfourth';
	const calls: Array<{ line: number; id: string }> = [];
	let holdInitialThird: ((value: ReturnType<typeof result>) => void) | null = null;
	let initialThirdStarted: (() => void) | null = null;
	const initialThirdReady = new Promise<void>((resolve) => { initialThirdStarted = resolve; });
	let releaseThirdRefresh: (() => void) | null = null;
	let thirdRefreshStarted: (() => void) | null = null;
	const thirdRefreshReady = new Promise<void>((resolve) => { thirdRefreshStarted = resolve; });
	const thirdRefresh = new Promise<void>((resolve) => { releaseThirdRefresh = resolve; });
	let releaseResumeStartup: (() => void) | null = null;
	let resumeStartupStarted: (() => void) | null = null;
	const resumeStartupReady = new Promise<void>((resolve) => { resumeStartupStarted = resolve; });
	const resumeStartup = new Promise<void>((resolve) => { releaseResumeStartup = resolve; });
	const restored: unknown[] = [];
	const captured = {
		stage1Model: 'provider/original', stage2Model: null, catalogId: 'sumi', catalogMode: 'fixed' as const,
		sketchGrain: 'fine', wild: true, canvasAspectId: 'square',
	};
	const runOptions = (resumeLines?: Array<{ line: number; input: string }>) => ({
		resumeLines,
		runConditions: captured,
		canvasAspectId: 'square',
		maxRetries: 0,
		paintLine: async (_text: string, options: { batchLineNumber?: number; batchRunId?: string }) => {
			const line = options.batchLineNumber!;
			calls.push({ line, id: options.batchRunId! });
			if (line === 3 && calls.filter((call) => call.line === 3).length === 1) {
				initialThirdStarted?.();
				return await new Promise<ReturnType<typeof result>>((resolve) => { holdInitialThird = resolve; });
			}
			return result(line);
		},
		onLatestResult: () => {},
		refreshAfterServerSave: async () => {
			if (calls.at(-1)?.line === 3 && calls.filter((call) => call.line === 3).length === 2) {
				thirdRefreshStarted?.();
				await thirdRefresh;
			}
		},
		refreshAfterRun: async () => {},
	});

	const firstRun = state.run(runOptions());
	await initialThirdReady;
	state.stop();
	holdInitialThird?.(result(3));
	await firstRun;
	assert.deepEqual(state.resumeInfo, { nextLine: 3, pending: 2, total: 3 });

	const firstResume = state.resumeInterrupted({
		blocked: () => false,
		applyConditions: (conditions) => { restored.push(conditions); },
		run: async (lines) => {
			resumeStartupStarted?.();
			await resumeStartup;
			return state.run(runOptions(lines));
		},
	});
	await resumeStartupReady;
	assert.equal(state.resuming, true);
	let duplicateStarts = 0;
	await state.resumeInterrupted({
		blocked: () => false,
		applyConditions: () => {},
		run: async () => { duplicateStarts += 1; },
	});
	assert.equal(duplicateStarts, 0);
	releaseResumeStartup?.();
	await thirdRefreshReady;
	assert.equal(state.resuming, false);
	state.stop();
	releaseThirdRefresh?.();
	await firstResume;
	assert.deepEqual(state.resumeInfo, { nextLine: 4, pending: 1, total: 3 });

	await state.resumeInterrupted({
		blocked: () => false,
		applyConditions: (conditions) => { restored.push(conditions); },
		run: (lines) => state.run(runOptions(lines)),
	});

	assert.deepEqual(calls.map((call) => call.line), [1, 3, 3, 4]);
	assert.deepEqual(calls.map((call) => call.id), ['run-original', 'run-original', 'run-original', 'run-original']);
	assert.deepEqual(restored, [captured, captured]);
	assert.equal(state.resume, null);
});

test('T-809: stopping before the first saved line leaves that first line resumable', async () => {
	const { state } = makeState();
	state.input = 'first';
	let release: ((value: ReturnType<typeof result>) => void) | null = null;
	let started: (() => void) | null = null;
	const ready = new Promise<void>((resolve) => { started = resolve; });
	const run = state.run({
		canvasAspectId: 'square', maxRetries: 0,
		paintLine: async () => {
			started?.();
			return await new Promise<ReturnType<typeof result>>((resolve) => { release = resolve; });
		},
		onLatestResult: () => {}, refreshAfterServerSave: async () => {}, refreshAfterRun: async () => {},
	});
	await ready;
	state.stop();
	release?.(result(1));
	await run;
	assert.deepEqual(state.resumeInfo, { nextLine: 1, pending: 1, total: 1 });
	state.clearPromptHistory();
	await state.refreshResume();
	assert.equal(state.resume, null);
	assert.deepEqual(state.resumeInfo, { nextLine: null, pending: null, total: 0 });
});

test('T-810: an account reset while history recovery is pending cannot start its stale resume', async () => {
	let releaseWorks: ((value: Response) => void) | null = null;
	const worksReady = new Promise<Response>((resolve) => { releaseWorks = resolve; });
	const prompt = 'first\nsecond';
	const newest = { batch_line_number: 1, batch_run_id: 'saved-run', source_text: 'first' };
	const { state } = makeState(async (path) => {
		if (path.includes('limit=20')) return jsonResponse({ items: [newest] });
		if (path.includes('limit=100')) return await worksReady;
		return jsonResponse({ items: [] });
	});
	state.promptHistory = [prompt];
	await state.refreshResume();
	let starts = 0;
	const options = {
		blocked: () => false,
		applyConditions: () => {},
		run: async () => { starts += 1; },
	};
	const first = state.resumeInterrupted(options);
	state.clearPromptHistory();
	releaseWorks?.(jsonResponse({ items: [newest] }));
	await first;
	assert.equal(starts, 0);
	assert.equal(state.resume, null);
});

test('T-811: failed ancillary refreshes neither retry a saved line nor hide an interrupted resume', async () => {
	const { state } = makeState(undefined, undefined, () => {});
	state.input = 'first\nsecond';
	let paints = 0;
	let releaseSecond: ((value: ReturnType<typeof result>) => void) | null = null;
	let secondStarted: (() => void) | null = null;
	const secondReady = new Promise<void>((resolve) => { secondStarted = resolve; });
	const run = state.run({
		canvasAspectId: 'square', maxRetries: 1,
		paintLine: async (_text, options) => {
			paints += 1;
			if (options.batchLineNumber === 2) {
				secondStarted?.();
				return await new Promise<ReturnType<typeof result>>((resolve) => { releaseSecond = resolve; });
			}
			return result(1);
		},
		onLatestResult: () => {},
		refreshAfterServerSave: async () => { throw new Error('history unavailable'); },
		refreshAfterRun: async () => { throw new Error('final history unavailable'); },
	});
	await secondReady;
	state.stop();
	releaseSecond?.(result(2));
	await run;
	assert.equal(paints, 2);
	assert.equal(state.success, 1);
	assert.deepEqual(state.failures, []);
	assert.equal(state.canResume, true);
	assert.deepEqual(state.resumeInfo, { nextLine: 2, pending: 1, total: 2 });
});

// A Server that goes away while a batch draws (a deploy restarted 5173's API under
// a batch on 2026-10-21, and every line sent while it was down stayed a failure).
// /api/info answers 502 while it is down, and it comes back at the probe `upAfter`.
function outageState(upAfter: number, options: { limitMs?: number; onSleep?: () => void } = {}) {
	const server = { down: false, probes: 0, saved: [] as Array<Record<string, unknown>> };
	let clock = 0;
	const reports: unknown[] = [];
	const state = new BatchState({
		apiFetch: async (path) => {
			if (path.startsWith('/api/pipeline/batches') || path === '/api/pipeline/activity') return new Response('', { status: 404 });
			if (path.startsWith('/api/info')) {
				server.probes += 1;
				if (server.down && server.probes >= upAfter) server.down = false;
				return server.down ? new Response('', { status: 502 }) : jsonResponse({ name: 'inku-server' });
			}
			if (server.down) return new Response('', { status: 502 });
			return jsonResponse({ items: path.startsWith('/api/history') ? server.saved : [] });
		},
		signedIn: () => true,
		paintable: (text) => text.trim().length > 0,
		setFailureReport: (report) => reports.push(report),
		createRunId: () => 'run-fixed',
		sleep: async (ms: number) => { clock += ms; options.onSleep?.(); },
		now: () => clock,
		serverWait: { limitMs: options.limitMs ?? 300_000, firstPhaseMs: 30_000, firstIntervalMs: 2_000, laterIntervalMs: 5_000 },
	});
	return { state, reports, server };
}

const quietRun = { canvasAspectId: 'square' as const, maxRetries: 0,
	onLatestResult: () => {}, refreshAfterServerSave: async () => {}, refreshAfterRun: async () => {} };

test('finished failures close differently from completion, a stop, or a lost connection', async () => {
	for (const scenario of ['success', 'failed', 'stopped', 'lost', 'unexpected'] as const) {
		const statuses: string[] = [];
		let reportWrites = 0;
		let state: InstanceType<typeof BatchState>;
		state = new BatchState({
			apiFetch: async (path, init) => {
				if (path === '/api/pipeline/batches' && init?.method === 'POST') return jsonResponse({ lease: 'lease' });
				if (path.endsWith('/heartbeat')) { statuses.push(JSON.parse(String(init?.body)).state); return jsonResponse({}); }
				if (path === '/api/pipeline/batches') return jsonResponse({ batches: [] });
				if (path === '/api/info') return new Response('', { status: 503 });
				return jsonResponse({ items: [] });
			},
			signedIn: () => true, paintable: (text) => !!text.trim(), setFailureReport: () => {
				if (scenario === 'unexpected' && ++reportWrites === 2) throw new Error('report failed');
			},
			createRunId: () => 'run-1', serverWait: { limitMs: 0, firstPhaseMs: 0, firstIntervalMs: 1, laterIntervalMs: 1 },
		});
		state.input = 'first\nsecond';
		const run = state.run({ ...quietRun, paintLine: async (_text, options) => {
			if (options.batchLineNumber === 2 && scenario === 'failed') throw new Error('failed');
			if (options.batchLineNumber === 2 && scenario === 'lost') throw new ConnectionFailure('cut', 'lost');
			if (options.batchLineNumber === 2 && scenario === 'stopped') state.stop();
			return result(options.batchLineNumber!);
		} });
		if (scenario === 'unexpected') await assert.rejects(run, /report failed/);
		else await run;
		assert.equal(statuses.at(-1), scenario === 'success' ? 'completed' : scenario === 'failed' ? 'finished_with_failures' : 'interrupted', scenario);
	}
});

test('finished failures offer failed lines while interruptions keep their existing notice', async () => {
	const conditions = { stage1Model: null, stage2Model: null, catalogId: null, catalogMode: null,
		sketchGrain: null, wild: null, canvasAspectId: null };
	const record = { run_id: 'run-1', kind: 'web', total: 3, completed: 2,
		state: 'finished_with_failures', prompt: 'one\ntwo\nthree', conditions, updated_at: 1 };
	const state = new BatchState({ apiFetch: async (path) => path === '/api/pipeline/batches'
		? jsonResponse({ batches: [record] }) : jsonResponse({ items: [
			{ batch_run_id: 'run-1', batch_line_number: 1 }, { batch_run_id: 'run-1', batch_line_number: 3 },
		] }), signedIn: () => true, paintable: (text) => !!text.trim(), setFailureReport: () => {} });
	await state.refreshResume();
	assert.equal(state.canResume, true);
	assert.deepEqual(state.resumeInfo, { nextLine: null, pending: null, total: 3, reason: 'failed', failureCount: 1 });
	assert.equal(ja.batchFailedResumeTitle, '描けなかった行を描き直す');
	assert.equal(ja.batchFailedResumeDescription(3, 1), '元のバッチ（3 件）で描けなかった 1 件を描きます。');
	assert.equal(en.batchFailedResumeTitle, 'Draw the lines that failed');
	assert.equal(en.batchFailedResumeDescription(3, 1), 'Draws the 1 line of the original batch (3) that was not drawn.');
	assert.equal(en.batchFailedResumeDescription(50, 2), 'Draws the 2 lines of the original batch (50) that were not drawn.');
	let sent: number[] = [];
	await state.resumeInterrupted({ blocked: () => false, applyConditions: () => {}, run: async (lines) => { sent = lines.map((line) => line.line); } });
	assert.deepEqual(sent, [2]);
	const reopened = new BatchState({ apiFetch: async () => jsonResponse({ batches: [{ ...record, state: 'interrupted' }] }),
		signedIn: () => true, paintable: (text) => !!text.trim(), setFailureReport: () => {} });
	await reopened.refreshResume();
	assert.equal(reopened.canResume, true);
	assert.equal(reopened.resume?.reason, undefined);
});

test('the same run failure report suppresses only its duplicate failure notice', async () => {
	const conditions = { stage1Model: null, stage2Model: null, catalogId: null, catalogMode: null,
		sketchGrain: null, wild: null, canvasAspectId: null };
	const record = { run_id: 'run-1', kind: 'web', total: 2, completed: 1, state: 'finished_with_failures',
		prompt: 'one\ntwo', conditions, updated_at: 1 };
	let report: BatchFailureReport | null = { success: 1, total: 2, failures: [{ line: 2, input: 'two', message: 'failed' }],
		retry: { prompt: record.prompt, runId: 'run-1', conditions, failedLines: [2], pendingLines: [2] } };
	const state = new BatchState({ apiFetch: async () => jsonResponse({ batches: [record] }),
		signedIn: () => true, paintable: (text) => !!text.trim(), setFailureReport: () => {}, getFailureReport: () => report });
	await state.refreshResume();
	assert.equal(state.canResume, false);
	report = { ...report!, retry: { ...report!.retry!, runId: 'another' } };
	assert.equal(state.canResume, true);
	report = null;
	assert.equal(state.canResume, true);
});

test('a batch waits for the Server through a restart and sends the cut lines again, failing none (Q1, Q2)', async () => {
	const { state, server } = outageState(3);
	state.input = 'one\ntwo\nthree\nfour\nfive';
	const calls: number[] = [];
	await state.run({ ...quietRun, paintLine: async (_text, options) => {
		const line = options.batchLineNumber!;
		calls.push(line);
		if (line === 2 && calls.filter((call) => call === 2).length === 1) {
			server.down = true;
			throw new ConnectionFailure('cut', 'paint stream ended before completion');
		}
		if (server.down) throw new ConnectionFailure('gateway', 'HTTP 502');
		return result(line);
	} });
	assert.deepEqual(state.failures, []);
	assert.deepEqual(calls, [1, 2, 2, 3, 4, 5]);
	assert.equal(state.success, 5);
	assert.equal(state.interrupted, false);
	assert.equal(server.probes, 3);
	assert.equal(state.waitingForServer, null);
});

test('a line the Server saved before its stream was cut is not drawn again (Q3)', async () => {
	const { state, server } = outageState(2);
	state.input = 'one\ntwo\nthree';
	const calls: number[] = [];
	await state.run({ ...quietRun, paintLine: async (_text, options) => {
		const line = options.batchLineNumber!;
		calls.push(line);
		if (line === 2) {
			server.saved.push({ id: 'work-2', batch_run_id: 'run-fixed', batch_line_number: 2 });
			server.down = true;
			throw new ConnectionFailure('cut', 'paint stream ended before completion');
		}
		return result(line);
	} });
	assert.deepEqual(calls, [1, 2, 3]);
	assert.deepEqual(state.failures, []);
	assert.equal(state.success, 3);
});

test('a Server that does not come back within the wait interrupts the batch, which resumes from that line (Q4)', async () => {
	const { state, server } = outageState(Number.POSITIVE_INFINITY, { limitMs: 60_000 });
	state.input = 'one\ntwo\nthree';
	const calls: number[] = [];
	await state.run({ ...quietRun, paintLine: async (_text, options) => {
		const line = options.batchLineNumber!;
		calls.push(line);
		if (line === 2) {
			server.down = true;
			throw new ConnectionFailure('unreachable', 'Failed to fetch');
		}
		return result(line);
	} });
	assert.deepEqual(calls, [1, 2]);
	assert.deepEqual(state.failures, []);
	assert.equal(state.interrupted, true);
	assert.equal(state.serverLost, true);
	assert.deepEqual(state.resume?.pending?.map((line) => line.line), [2, 3]);
});

test('a failure the Server answered is counted as before, without waiting (Q5)', async () => {
	const { state, server } = outageState(1);
	state.input = 'one\ntwo';
	await state.run({ ...quietRun, paintLine: async (_text, options) => {
		if (options.batchLineNumber === 1) throw new Error('503: provider down');
		return result(2);
	} });
	assert.deepEqual(state.failures.map((failure) => [failure.line, failure.message]), [[1, '503: provider down']]);
	assert.equal(server.probes, 0);
	assert.equal(state.serverLost, false);
});

test('stopping while the batch waits for the Server interrupts it at once (Q6)', async () => {
	let stop = () => {};
	const { state, server } = outageState(Number.POSITIVE_INFINITY, { onSleep: () => stop() });
	stop = () => state.stop();
	state.input = 'one\ntwo\nthree';
	const calls: number[] = [];
	await state.run({ ...quietRun, paintLine: async (_text, options) => {
		const line = options.batchLineNumber!;
		calls.push(line);
		if (line === 2) {
			server.down = true;
			throw new ConnectionFailure('gateway', 'HTTP 502');
		}
		return result(line);
	} });
	assert.deepEqual(calls, [1, 2]);
	assert.deepEqual(state.failures, []);
	assert.equal(state.interrupted, true);
	assert.equal(state.serverLost, false);
	assert.equal(server.probes, 1);
});

test('a line cut three times in a row while the Server answers is counted as a failure', async () => {
	const { state, server } = outageState(1);
	state.input = 'one';
	const calls: number[] = [];
	await state.run({ ...quietRun, paintLine: async (_text, options) => {
		calls.push(options.batchLineNumber!);
		throw new ConnectionFailure('cut', 'paint stream ended before completion');
	} });
	assert.deepEqual(calls, [1, 1, 1]);
	assert.deepEqual(state.failures.map((failure) => [failure.line, failure.message]), [[1, 'paint stream ended before completion']]);
	assert.equal(server.probes, 2);
});

test('a dismissed lease stays hidden after refresh and a new batch remains eligible', async () => {
	const values = new Map<string, string>();
	const oldStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
	Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
		getItem: (key: string) => values.get(key) ?? null,
		setItem: (key: string, value: string) => values.set(key, value),
	} });
	try {
		const conditions = { stage1Model: null, stage2Model: null, catalogId: null, catalogMode: null,
			sketchGrain: null, wild: null, canvasAspectId: null };
		let runId = 'dismiss-test-old';
		const make = () => new BatchState({
			apiFetch: async () => jsonResponse({ batches: [{ run_id: runId, kind: 'web', total: 2, completed: 1,
				state: 'interrupted', prompt: 'first\nsecond', conditions }] }),
			signedIn: () => true, paintable: (text) => !!text.trim(), setFailureReport: () => {},
		});
		const state = make();
		await state.refreshResume();
		assert.equal(state.resume?.runId, runId);
		state.clearInput();
		assert.match(values.get('inku.batch.dismissedRuns.v1') ?? '', /dismiss-test-old/);
		await state.refreshResume();
		assert.equal(state.resume, null);
		const reopened = make();
		await reopened.refreshResume();
		assert.equal(reopened.resume, null);
		// Simulate a fresh page: this id exists only in persisted storage, not in
		// this module's in-memory set.
		values.set('inku.batch.dismissedRuns.v1', JSON.stringify(['dismiss-test-from-storage']));
		runId = 'dismiss-test-from-storage';
		await reopened.refreshResume();
		assert.equal(reopened.resume, null);
		runId = 'dismiss-test-new';
		await reopened.refreshResume();
		assert.equal(reopened.resume?.runId, runId);
	} finally {
		if (oldStorage) Object.defineProperty(globalThis, 'localStorage', oldStorage);
		else Reflect.deleteProperty(globalThis, 'localStorage');
	}
});
