import assert from 'node:assert/strict';
import { test } from 'node:test';

const identity = <T>(value: T): T => value;
const stateShim = identity as (<T>(value: T) => T) & { raw: <T>(value: T) => T };
stateShim.raw = identity;
const runeHost = globalThis as unknown as Record<string, unknown>;
runeHost.$state = stateShim;
runeHost.$derived = identity;

const { BatchState } = await import('./state.svelte.ts');

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

function makeState(apiFetch: (path: string, init?: RequestInit) => Promise<Response> = async () => jsonResponse({ items: [] })) {
	const reports: unknown[] = [];
	const state = new BatchState({
		apiFetch,
		signedIn: () => true,
		paintable: (text) => text.trim().length > 0,
		setFailureReport: (report) => reports.push(report),
		createRunId: () => 'run-fixed',
	});
	return { state, reports };
}

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
	assert.equal(state.resume, null);
	assert.deepEqual(resumed, [{ line: 3, input: 'third' }]);
	assert.equal((restored as { stage1Model?: string }).stage1Model, 'provider/model-1');
	assert.match(requests.at(-1)?.path ?? '', /limit=100/);
});
