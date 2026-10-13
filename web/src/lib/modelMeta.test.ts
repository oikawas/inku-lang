// Run with: node --import ./scripts/ts-extensionless-resolve.mjs --test src/lib/modelMeta.test.ts
//
// What the model card prints from the measured reference numbers and the
// purposes (the author's tooltip request, 2026-10-13). The levels have their own
// check in scripts/model-recommendation-check.mjs.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { isModelUnselectable, modelCost, modelFold, modelPurposeBadges, modelSpeed, modelStatusLabel } from './modelMeta';

test('both purposes are listed, and the one a model cannot be chosen for is marked', () => {
	assert.deepEqual(
		modelPurposeBadges({ id: 'x', label: 'x', purposes: ['vision'] }).map(({ label, selectable }) => [label, selectable]),
		[['LLM', false], ['Vision', true]]
	);
	// A model whose purposes are not stated is an LLM, as everywhere else.
	assert.deepEqual(modelPurposeBadges({ id: 'x', label: 'x' }).map((badge) => badge.selectable), [true, false]);
});

test('a purpose measured without a response is greyed, and a model with neither cannot be chosen', () => {
	const drawsNothing = { id: 'x', label: 'x', purposes: ['llm', 'vision'] as ('llm' | 'vision')[], unsupported_purposes: ['llm'] as ('llm' | 'vision')[] };
	assert.deepEqual(modelPurposeBadges(drawsNothing).map((badge) => badge.selectable), [false, true]);
	assert.equal(isModelUnselectable(drawsNothing), false);
	const answersNothing = { id: 'x', label: 'x', purposes: [], unsupported_purposes: ['llm', 'vision'] as ('llm' | 'vision')[] };
	assert.equal(isModelUnselectable(answersNothing), true);
	assert.equal(modelStatusLabel(answersNothing, true), '計測で応答なし');
});

test('models that cannot be published are filed into their folds; a usable one stays in the list', () => {
	const both = ['llm', 'vision'] as ('llm' | 'vision')[];
	const folds = [
		{ id: 'retired', label: 'x', eol: true, not_supported: true },
		{ id: 'tts', label: 'x', not_supported: true },
		{ id: 'silent', label: 'x', purposes: [], unsupported_purposes: both },
		{ id: 'vision-only', label: 'x', purposes: ['vision'] as ('llm' | 'vision')[], unsupported_purposes: ['llm'] as ('llm' | 'vision')[] },
		{ id: 'paid', label: 'x', requires_subscription: true }
	].map((model) => [model.id, modelFold(model), isModelUnselectable(model)]);
	assert.deepEqual(folds, [
		['retired', 'eol', true], ['tts', 'not_supported', true], ['silent', 'no_response', true],
		['vision-only', null, false], ['paid', null, true]
	]);
	assert.equal(modelStatusLabel({ id: 'tts', label: 'x', not_supported: true }, true), 'ノンサポート');
});

test('cost prints per drawing and per image, and a free model costs $0 rather than nothing', () => {
	const model = { id: 'x', label: 'x', cost_usd_llm: 0.007718, cost_usd_vision: 0 };
	assert.equal(modelCost(model, true), 'LLM $0.0077（描画1回） / Vision $0（画像1枚）');
	assert.equal(modelCost(model, false), 'LLM $0.0077 per drawing / Vision $0 per picture');
	assert.equal(modelCost({ id: 'x', label: 'x' }, true), '—');
});

test('measured means read as a reference and replace the old label; an unmeasured model keeps it', () => {
	const measured = { id: 'x', label: 'x', speed_label: '中央値 11s', speed_llm_seconds: 12.53, speed_vision_seconds: 2.2 };
	assert.equal(modelSpeed(measured, true), 'LLM 平均 12.5秒 / Vision 平均 2.2秒（参考値）');
	assert.equal(modelSpeed(measured, false), 'LLM mean 12.5 s / Vision mean 2.2 s (reference)');
	assert.equal(modelSpeed({ id: 'x', label: 'x', speed_label: '中央値 11s' }, true), '中央値 11s');
});
