#!/usr/bin/env node
// model-ref-check — the browser half of model reference resolution.
//
//   npm run lint:models
//
// It reads model-ref-expectations.json, the same file
// server/tests/test_model_ref_qualification.py reads, and asserts that
// src/lib/models.ts answers exactly what the server answers. Two tables that
// agree today would drift; one table cannot.
//
// There is no test runner in web/ on purpose — this is a plain node script, the
// same shape as i18n-lint.mjs. Node strips the TypeScript types on import.

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const EXPECTATIONS = JSON.parse(readFileSync(join(HERE, 'model-ref-expectations.json'), 'utf8'));

const { splitModelRef, qualifiedModelId, resolveModelRef } = await import(
	join(HERE, '..', 'src/lib/models.ts')
);

const failures = [];
let checks = 0;

function check(what, actual, expected) {
	checks += 1;
	const a = JSON.stringify(actual);
	const e = JSON.stringify(expected);
	if (a !== e) failures.push(`${what}\n    expected ${e}\n    actual   ${a}`);
}

/** The catalog as ProviderGroup[], so the rules read the server's model lists. */
function groupsFrom(catalog, drop = null) {
	return Object.entries(catalog)
		.filter(([id]) => id !== drop)
		.map(([id, models]) => ({ id, label: id, models: models.map((m) => ({ id: m, label: m })) }));
}

const GROUPS = groupsFrom(EXPECTATIONS.catalog);
const STAGE1 = EXPECTATIONS.stage_defaults.stage1_provider;
const STAGE2 = EXPECTATIONS.stage_defaults.stage2_provider;

// ── the expectation table ─────────────────────────────────────────────────
for (const c of EXPECTATIONS.cases) {
	for (const [stage, fallback] of [['stage1', STAGE1], ['stage2', STAGE2]]) {
		check(
			`resolve ${c.ref} (${stage}, rule ${c.rule})`,
			resolveModelRef(c.ref, GROUPS, fallback),
			{ provider: c.provider, model: c.model }
		);
	}
}

// ── rule 3 reads the stage ────────────────────────────────────────────────
{
	const { stage1_provider, stage2_provider } = EXPECTATIONS.stage_dependent.stage_defaults;
	for (const c of EXPECTATIONS.stage_dependent.cases) {
		check(`stage-dependent ${c.ref} stage1`, resolveModelRef(c.ref, GROUPS, stage1_provider).provider, c.stage1);
		check(`stage-dependent ${c.ref} stage2`, resolveModelRef(c.ref, GROUPS, stage2_provider).provider, c.stage2);
	}
}

// ── rule 2 demands exactly one owner ──────────────────────────────────────
{
	const a = EXPECTATIONS.ambiguity;
	const owners = Object.entries(EXPECTATIONS.catalog)
		.filter(([, models]) => models.includes(a.ref))
		.map(([id]) => id);
	check(`${a.ref} is offered by both providers`, owners.sort(), [...a.owners].sort());
	check(`${a.ref} is not decided by rule 2`, resolveModelRef(a.ref, GROUPS, STAGE1).provider, STAGE1);
	check(
		`${a.ref} is decided once ${a.deactivate} is gone`,
		resolveModelRef(a.ref, groupsFrom(EXPECTATIONS.catalog, a.deactivate), STAGE1).provider,
		a.provider_when_deactivated
	);
}

// ── nothing unrecognised lands on ovms ────────────────────────────────────
for (const ref of EXPECTATIONS.never_ovms.refs) {
	const provider = resolveModelRef(ref, GROUPS, 'ollama').provider;
	check(`${ref} does not land on ovms`, provider === 'ovms', false);
}

// ── qualification never happens twice ─────────────────────────────────────
for (const c of EXPECTATIONS.qualify) {
	check(`qualify(${c.provider}, ${c.ref})`, qualifiedModelId(c.provider, c.ref, GROUPS), c.expected);
}

// ── a model id carrying colons survives the round trip ────────────────────
for (const c of EXPECTATIONS.round_trip) {
	const qualified = qualifiedModelId(c.provider, c.model, GROUPS);
	check(`qualify ${c.provider} + ${c.model}`, qualified, `${c.provider}:${c.model}`);
	check(`split ${qualified}`, splitModelRef(qualified, GROUPS), { provider: c.provider, model: c.model });
}

// ── the JavaScript trap this rule was rewritten around ────────────────────
// 'a:b:c'.split(':', 1) returns ['a'] — the limit drops the tail rather than
// capping the number of splits the way Python does. splitModelRef must not
// lose anything after the model id's own colon.
check(
	"split('ollama-cloud:gemma4:31b') keeps the tail",
	splitModelRef('ollama-cloud:gemma4:31b', GROUPS),
	{ provider: 'ollama-cloud', model: 'gemma4:31b' }
);
check('an empty model id is not a qualification', splitModelRef('ollama:', GROUPS), {
	provider: null,
	model: 'ollama:'
});
check('a leading colon is not a qualification', splitModelRef(':leading', GROUPS), {
	provider: null,
	model: ':leading'
});

if (failures.length > 0) {
	console.error(`model-ref-check: ${failures.length} of ${checks} checks failed\n`);
	for (const failure of failures) console.error(`  ✗ ${failure}\n`);
	process.exit(1);
}
console.log(`model-ref-check: ${checks} checks passed`);
