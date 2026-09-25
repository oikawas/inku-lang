import assert from 'node:assert/strict';
import { test } from 'node:test';

import { loadSystemPrompts } from './system-prompts';

test('the prompt tab tells a recorded prompt from an unrecorded or unreadable one', async () => {
	const sent = {
		system: 'work planner…',
		prompt_id: 'inku.typed-stage1-work-plan-prompt.v1',
		prompt_digest: 'abc',
		instruction_language: 'ja',
		attempt: 1
	};
	const paths: string[] = [];
	const answering = (status: number, body: unknown) => async (path: string) => {
		paths.push(path);
		return new Response(JSON.stringify(body), { status });
	};

	assert.deepEqual(
		await loadSystemPrompts('variation/1', answering(200, { recorded: true, stage1: sent, stage2: null })),
		{ state: 'recorded', stage1: sent, stage2: null }
	);
	assert.deepEqual(paths, ['/api/pipeline/variations/variation%2F1/system-prompts']);
	assert.deepEqual(await loadSystemPrompts('v', answering(200, { recorded: false })), { state: 'not_recorded' });
	assert.deepEqual(await loadSystemPrompts(null, answering(200, {})), { state: 'not_recorded' });
	assert.deepEqual(await loadSystemPrompts('v', answering(404, {})), { state: 'unavailable' });
});
