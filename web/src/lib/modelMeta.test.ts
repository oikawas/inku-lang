// Run with: node --import ./scripts/ts-extensionless-resolve.mjs --test src/lib/modelMeta.test.ts
//
// What the model card prints from the measured reference numbers and the
// purposes (the author's tooltip request, 2026-10-13). The levels have their own
// check in scripts/model-recommendation-check.mjs.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { isModelUnselectable, modelCost, modelFold, modelFoldTitle, modelFolds, modelPurposeBadges, modelSpeed, modelStatusLabel, modelStatusParts, purposeUnsupported, setModelLabelTable, sortModels } from './modelMeta';
import type { ModelLabel, ModelOption } from './models';

// The Server's model catalog and the cases every client checks itself against (2026-10-13).
const catalog = JSON.parse(readFileSync(new URL('../../../server/src/inku_server/model_catalog.json', import.meta.url), 'utf8')) as { labels: ModelLabel[] };
const cases = JSON.parse(readFileSync(new URL('../../../server/tests/data/model-catalog-cases.json', import.meta.url), 'utf8')) as {
	cases: { name: string; labels: string[]; fold: string | null; publishable: boolean }[];
};
setModelLabelTable(catalog.labels);

test('both purposes are listed, and the one a model cannot be chosen for is marked', () => {
	assert.deepEqual(
		modelPurposeBadges({ id: 'x', label: 'x', purposes: ['vision'] }).map(({ label, selectable }) => [label, selectable]),
		[['LLM', false], ['Vision', true]]
	);
	// A model whose purposes are not stated is an LLM, as everywhere else.
	assert.deepEqual(modelPurposeBadges({ id: 'x', label: 'x' }).map((badge) => badge.selectable), [true, false]);
});

test('a purpose measured without a response is not recommended, and a model with neither can still be chosen', () => {
	const drawsNothing = { id: 'x', label: 'x', purposes: ['vision'] as ('llm' | 'vision')[], unsupported_purposes: ['llm'] as ('llm' | 'vision')[], labels: [], fold: null };
	assert.deepEqual(modelPurposeBadges(drawsNothing).map((badge) => badge.selectable), [false, true]);
	assert.equal(isModelUnselectable(drawsNothing), false);
	assert.deepEqual([purposeUnsupported(drawsNothing, 'llm'), purposeUnsupported(drawsNothing, 'vision')], [true, false]);
	// Chosen against the measurement (2026-10-26): publishable, its label still in the warning colour.
	const answersNothing = { id: 'x', label: 'x', purposes: ['llm'] as ('llm' | 'vision')[], unsupported_purposes: ['llm', 'vision'] as ('llm' | 'vision')[], labels: ['no_response'], fold: 'no_response' };
	assert.equal(isModelUnselectable(answersNothing), false);
	assert.deepEqual(modelStatusParts(answersNothing, true), [{ text: '計測で応答なし', blocking: true }]);
	assert.equal(isModelUnselectable({ id: 'x', label: 'x', unsupported_purposes: ['llm', 'vision'] }), false);
});

test('a model chosen for a purpose it did not answer is listed after those that answered it', () => {
	const answered = { id: 'b', label: 'b', recommendation_llm: 1 };
	const unanswered = { id: 'a', label: 'a', purposes: ['llm'] as ('llm' | 'vision')[], unsupported_purposes: ['llm'] as ('llm' | 'vision')[], recommendation_llm: 5 };
	assert.deepEqual(sortModels([unanswered, answered], 'llm').map((model) => model.id), ['b', 'a']);
});

test('the labels the Server worked out decide the fold and the publication, as the shared cases say', () => {
	assert.deepEqual(modelFolds(), ['unmeasured', 'legacy', 'subscription', 'no_response', 'not_supported', 'eol']);
	for (const entry of cases.cases) {
		const model: ModelOption = { id: 'x', label: 'x', labels: entry.labels, fold: entry.fold };
		assert.deepEqual([modelFold(model), !isModelUnselectable(model)], [entry.fold, entry.publishable], entry.name);
	}
	assert.equal(cases.cases.length, 15);
});

test('a model shows every label it carries, and a fold is titled from the table', () => {
	const retired = { id: 'x', label: 'x', labels: ['legacy', 'eol'], fold: 'eol', eol_date: '2026-10-13' };
	assert.equal(modelStatusLabel(retired, true), '旧モデル · 提供終了 (2026-10-13)');
	assert.equal(modelStatusLabel(retired, false), 'Older model · End of life (2026-10-13)');
	assert.equal(modelStatusLabel({ id: 'x', label: 'x', labels: [], fold: null }, true), null);
	assert.equal(modelFoldTitle('unmeasured', 5, true), '未計測（5）');
	assert.equal(modelFoldTitle('legacy', 46, false), 'Older model (46)');
});

test('each label keeps its own colour: only one that keeps the model from publication warns', () => {
	const retired = { id: 'x', label: 'x', labels: ['legacy', 'eol'], fold: 'eol', eol_date: '2026-10-13' };
	assert.deepEqual(modelStatusParts(retired, true), [
		{ text: '旧モデル', blocking: false },
		{ text: '提供終了 (2026-10-13)', blocking: true }
	]);
	assert.deepEqual(modelStatusParts({ id: 'x', label: 'x', labels: ['unmeasured'], fold: 'unmeasured' }, false), [
		{ text: 'Not measured', blocking: false }
	]);
	assert.deepEqual(modelStatusParts({ id: 'x', label: 'x', labels: [], fold: null }, true), []);
});

test('the startup list, which has no labels yet, keeps to its stored marks', () => {
	assert.equal(isModelUnselectable({ id: 'paid', label: 'x', requires_subscription: true }), true);
	assert.equal(isModelUnselectable({ id: 'free', label: 'x' }), false);
	assert.equal(modelFold({ id: 'paid', label: 'x', requires_subscription: true }), null);
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
