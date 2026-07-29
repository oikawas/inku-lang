#!/usr/bin/env node
// model-recommendation-check — the browser half of recommendation levels.
//
//   npm run lint:recommendations
//
// It reads model-recommendation-expectations.json, the same file
// server/tests/test_model_recommendation.py reads, and asserts that
// src/lib/modelMeta.ts hands back what the catalog states. The server owns the
// values; this owns what the picker does with them.
//
// Plain node script, no test runner in web/ — the same shape as i18n-lint.mjs
// and model-ref-check.mjs. Node strips the TypeScript types on import.

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const EXPECTATIONS = JSON.parse(
	readFileSync(join(HERE, 'model-recommendation-expectations.json'), 'utf8')
);

const { modelRecommendationLevel, modelRecommendation, sortModels } = await import(
	join(HERE, '..', 'src/lib/modelMeta.ts')
);

const failures = [];
let checks = 0;

function check(what, actual, expected) {
	checks += 1;
	const a = JSON.stringify(actual);
	const e = JSON.stringify(expected);
	if (a !== e) failures.push(`${what}\n    expected ${e}\n    actual   ${a}`);
}

// ── the three stages read the right key ───────────────────────────────────
for (const c of EXPECTATIONS.display.cases) {
	const model = { id: 'x', label: 'x', ...c.model };
	for (const stage of ['stage1', 'stage2', 'both']) {
		check(`${JSON.stringify(c.model)} as ${stage}`, modelRecommendationLevel(model, 'llm', stage), c[stage]);
	}
}

// ── an unmeasured stage is an em dash, never zero stars ───────────────────
{
	const model = { id: 'x', label: 'x', recommendation_stage1: 1 };
	check('unmeasured stage renders as an em dash', modelRecommendation(model, 'llm', 'stage2'), '—');
	check('a measured 1 renders as one star', modelRecommendation(model, 'llm', 'stage1'), '★☆☆☆☆ (1/5)');
}

// ── omitting the stage keeps the old answer ───────────────────────────────
// Every surface that has no stage in question (the admin metadata editor, the
// history label) must be unaffected by the stage keys existing.
{
	const staged = { id: 'x', label: 'x', recommendation_llm: 4, recommendation_stage1: 5, recommendation_stage2: 2 };
	check('no stage falls back to the LLM level', modelRecommendationLevel(staged, 'llm'), 4);
	check('no purpose and no stage still reads the LLM level', modelRecommendationLevel(staged), 4);
}

// ── vision is untouched by the stage keys ─────────────────────────────────
{
	const model = {
		id: 'x', label: 'x', purposes: ['vision'],
		recommendation_vision: 3, recommendation_stage1: 5, recommendation_stage2: 5
	};
	for (const stage of ['stage1', 'stage2', 'both']) {
		check(`vision ignores ${stage}`, modelRecommendationLevel(model, 'vision', stage), 3);
	}
}

// ── the order changes with the stage ──────────────────────────────────────
// This is the arrangement's visible consequence: the same two models swap places
// between the Stage 1 tab and the Stage 2 tab.
{
	const s1Model = { id: 'stage1-strong', label: 'a', recommendation_stage1: 5, recommendation_stage2: 2 };
	const s2Model = { id: 'stage2-strong', label: 'b', recommendation_stage1: 3, recommendation_stage2: 5 };
	const ids = (stage) => sortModels([s1Model, s2Model], 'llm', stage).map((m) => m.id);
	check('Stage 1 tab leads with the Stage 1 model', ids('stage1'), ['stage1-strong', 'stage2-strong']);
	check('Stage 2 tab leads with the Stage 2 model', ids('stage2'), ['stage2-strong', 'stage1-strong']);
	check('the shared tab leads with the higher floor', ids('both'), ['stage2-strong', 'stage1-strong']);
}

if (failures.length > 0) {
	console.error(`model-recommendation-check: ${failures.length} of ${checks} checks failed\n`);
	for (const failure of failures) console.error(`  ${failure}\n`);
	process.exit(1);
}
console.log(`model-recommendation-check: ${checks} checks passed`);
