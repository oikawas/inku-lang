import assert from 'node:assert/strict';
import { test } from 'node:test';

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
		apiFetch,
		signedIn: () => true,
		paintable: (text) => text.trim().length > 0,
		setFailureReport: (report) => reports.push(report),
		createRunId,
		warn,
	});
	return { state, reports };
}

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
	const state = new BatchState({ apiFetch: async () => jsonResponse({ items: [] }), signedIn: () => true,
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

	await Promise.resolve();
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
