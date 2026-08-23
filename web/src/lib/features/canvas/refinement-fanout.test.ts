import assert from 'node:assert/strict';
import { setImmediate as waitForTurn } from 'node:timers/promises';
import { test } from 'node:test';

import type { VariationCandidate } from './refinement-session.svelte.ts';
import {
	planRefinementCandidates,
	runRefinementFanout,
	type RefinementFanoutCapabilities,
	type RefinementFanoutInput,
	type RefinementFanoutLabels
} from './refinement-fanout.ts';

const labels: RefinementFanoutLabels = {
	touch: 'Touch',
	layout: 'Layout',
	reading: 'Reading',
	variation: 'Variation',
	color: 'Color',
	noAlternateCatalog: 'No alternate catalog'
};

function candidate(id: string, compositionSeed?: number): VariationCandidate {
	return {
		id,
		label: id,
		selected: false,
		result: {
			ddl: '',
			thinking: null,
			composition_seed: compositionSeed
		}
	} as VariationCandidate;
}

function capabilities(
	overrides: Partial<RefinementFanoutCapabilities> = {}
): RefinementFanoutCapabilities {
	return {
		createCompositionSeed: () => 1,
		allocateVariationSeeds: async (_amplitude, count) => Array.from({ length: count }, (_, index) => index),
		catalogName: (id) => id.toUpperCase(),
		renderTouch: async (_words, label) => candidate(label),
		renderLayout: async (_seed, label) => candidate(label),
		renderReading: async (label) => candidate(label),
		renderVariation: async (_amplitude, _seed, label) => candidate(label),
		renderColor: async (_catalogId, label) => candidate(label),
		...overrides
	};
}

function input(overrides: Partial<RefinementFanoutInput> = {}): RefinementFanoutInput {
	return {
		kind: 'touch' as const,
		count: 1 as const,
		touchWords: 'soft ink',
		signal: new AbortController().signal,
		labels,
		currentCompositionSeed: null,
		previousCandidates: [] as VariationCandidate[],
		availableCatalogIds: ['current', 'a', 'b'],
		currentCatalogId: 'current',
		...overrides
	};
}

test('T-321: layout plan excludes displayed, existing, and newly allocated seeds', async () => {
	const exclusions: number[][] = [];
	const rendered: Array<{ seed: number; label: string; signal: AbortSignal }> = [];
	const signal = new AbortController().signal;
	const seeds = [30, 40, 50, 60];
	const plans = await planRefinementCandidates(
		input({
			kind: 'layout',
			count: 4,
			signal,
			currentCompositionSeed: 10,
			previousCandidates: [candidate('existing', 20), candidate('missing')]
		}),
		capabilities({
			createCompositionSeed: (excluded) => {
				exclusions.push([...excluded].sort((left, right) => left - right));
				return seeds.shift() ?? 0;
			},
			renderLayout: async (seed, label, receivedSignal) => {
				rendered.push({ seed, label, signal: receivedSignal });
				return candidate(label, seed);
			}
		})
	);

	assert.deepEqual(exclusions, [
		[10, 20],
		[10, 20, 30],
		[10, 20, 30, 40],
		[10, 20, 30, 40, 50]
	]);
	assert.deepEqual(plans.map((plan) => plan.label), ['Layout 1', 'Layout 2', 'Layout 3', 'Layout 4']);
	assert.deepEqual(
		(await Promise.all(plans.map((plan) => plan.run()))).map((item) => item.result.composition_seed),
		[30, 40, 50, 60]
	);
	assert.deepEqual(rendered.map(({ seed, label }) => ({ seed, label })), [
		{ seed: 30, label: 'Layout 1' },
		{ seed: 40, label: 'Layout 2' },
		{ seed: 50, label: 'Layout 3' },
		{ seed: 60, label: 'Layout 4' }
	]);
	assert.ok(rendered.every((entry) => entry.signal === signal));
});

test('T-322: variation plan allocates once and preserves amplitude, seed, and label order', async () => {
	const allocations: Array<{ amplitude: string; count: number }> = [];
	const renders: Array<{ amplitude: string; seed: number; label: string }> = [];
	const makePlans = async (amplitude?: 'small' | 'medium' | 'large') => planRefinementCandidates(
		input({ kind: 'variation', count: 4, amplitude }),
		capabilities({
			allocateVariationSeeds: async (resolvedAmplitude, count) => {
				allocations.push({ amplitude: resolvedAmplitude, count });
				return resolvedAmplitude === 'small' ? [7, 8, 9, 10] : [9, 10, 11, 12];
			},
			renderVariation: async (resolvedAmplitude, seed, label) => {
				renders.push({ amplitude: resolvedAmplitude, seed, label });
				return candidate(label);
			}
		})
	);

	const defaultPlans = await makePlans();
	const explicitPlans = await makePlans('small');
	await Promise.all([...defaultPlans, ...explicitPlans].map((plan) => plan.run()));

	assert.deepEqual(allocations, [
		{ amplitude: 'medium', count: 4 },
		{ amplitude: 'small', count: 4 }
	]);
	assert.deepEqual(defaultPlans.map((plan) => plan.label), [
		'Variation 1',
		'Variation 2',
		'Variation 3',
		'Variation 4'
	]);
	assert.deepEqual(renders, [
		{ amplitude: 'medium', seed: 9, label: 'Variation 1' },
		{ amplitude: 'medium', seed: 10, label: 'Variation 2' },
		{ amplitude: 'medium', seed: 11, label: 'Variation 3' },
		{ amplitude: 'medium', seed: 12, label: 'Variation 4' },
		{ amplitude: 'small', seed: 7, label: 'Variation 1' },
		{ amplitude: 'small', seed: 8, label: 'Variation 2' },
		{ amplitude: 'small', seed: 9, label: 'Variation 3' },
		{ amplitude: 'small', seed: 10, label: 'Variation 4' }
	]);
});

test('T-323: color plan excludes current, shuffles, cycles, labels, and rejects no alternate', async () => {
	const rendered: string[] = [];
	const plans = await planRefinementCandidates(
		input({ kind: 'color', count: 4, random: () => 0 }),
		capabilities({
			catalogName: (id) => `Catalog ${id}`,
			renderColor: async (catalogId, label) => {
				rendered.push(catalogId);
				return candidate(label);
			}
		})
	);

	assert.deepEqual(plans.map((plan) => plan.label), [
		'Color 1 · Catalog b',
		'Color 2 · Catalog a',
		'Color 3 · Catalog b',
		'Color 4 · Catalog a'
	]);
	await Promise.all(plans.map((plan) => plan.run()));
	assert.deepEqual(rendered, ['b', 'a', 'b', 'a']);
	await assert.rejects(
		planRefinementCandidates(input({ kind: 'color', availableCatalogIds: ['', 'current'] }), capabilities()),
		/No alternate catalog/
	);
});

test('T-324: touch and reading dispatch their exact arguments and shared signal', async () => {
	const calls: unknown[][] = [];
	const signal = new AbortController().signal;
	const shared = capabilities({
		renderTouch: async (...args) => { calls.push(['touch', ...args]); return candidate('touch'); },
		renderReading: async (...args) => { calls.push(['reading', ...args]); return candidate('reading'); }
	});
	const touchPlans = await planRefinementCandidates(input({ kind: 'touch', signal }), shared);
	const readingPlans = await planRefinementCandidates(input({ kind: 'reading', count: 4, signal }), shared);

	assert.deepEqual(touchPlans.map((plan) => plan.label), ['Touch']);
	assert.deepEqual(readingPlans.map((plan) => plan.label), ['Reading 1', 'Reading 2', 'Reading 3', 'Reading 4']);
	await Promise.all([...touchPlans, ...readingPlans].map((plan) => plan.run()));
	assert.deepEqual(calls, [
		['touch', 'soft ink', 'Touch', signal],
		['reading', 'Reading 1', signal],
		['reading', 'Reading 2', signal],
		['reading', 'Reading 3', signal],
		['reading', 'Reading 4', signal]
	]);
});

test('T-325: bounded executor preserves input order and indexed hooks across out-of-order completion', async () => {
	const releases: Array<() => void> = [];
	let inFlight = 0;
	let maximumInFlight = 0;
	const starts: number[] = [];
	const dones: number[] = [];
	const jobs = ['first', 'second', 'third'].map((value, index) => async () => {
		inFlight += 1;
		maximumInFlight = Math.max(maximumInFlight, inFlight);
		await new Promise<void>((resolve) => { releases[index] = resolve; });
		inFlight -= 1;
		return value;
	});
	const resultPromise = runRefinementFanout(jobs, 2, {
		onStart: (index) => { starts.push(index); },
		onDone: (index) => { dones.push(index); }
	});

	await waitForTurn();
	assert.deepEqual(starts, [0, 1]);
	releases[1]();
	await waitForTurn();
	assert.deepEqual(starts, [0, 1, 2]);
	releases[2]();
	releases[0]();

	assert.deepEqual(await resultPromise, ['first', 'second', 'third']);
	assert.equal(maximumInFlight, 2);
	assert.deepEqual(dones, [1, 2, 0]);
});
