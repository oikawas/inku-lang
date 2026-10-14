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
	layout: 'Layout',
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
		catalogName: (id) => id.toUpperCase(),
		renderLayout: async (_seed, label) => candidate(label),
		renderColor: async (_catalogId, label) => candidate(label),
		...overrides
	};
}

function input(overrides: Partial<RefinementFanoutInput> = {}): RefinementFanoutInput {
	return {
		kind: 'layout' as const,
		count: 1 as const,
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

test('T-323: color plan offers every other catalog in list order and rejects no alternate', async () => {
	const rendered: string[] = [];
	const plans = await planRefinementCandidates(
		input({ kind: 'color', count: 1, availableCatalogIds: ['a', 'current', '', 'b', 'c'] }),
		capabilities({
			catalogName: (id) => `Catalog ${id}`,
			renderColor: async (catalogId, label) => {
				rendered.push(catalogId);
				return candidate(label);
			}
		})
	);

	assert.deepEqual(plans.map((plan) => plan.label), ['Catalog a', 'Catalog b', 'Catalog c']);
	await Promise.all(plans.map((plan) => plan.run()));
	assert.deepEqual(rendered, ['a', 'b', 'c']);
	await assert.rejects(
		planRefinementCandidates(input({ kind: 'color', availableCatalogIds: ['', 'current'] }), capabilities()),
		/No alternate catalog/
	);
});

test('T-324: layout dispatches its exact arguments and shared signal', async () => {
	// It was the reading's test until another reading was removed (2026-10-14).
	const calls: unknown[][] = [];
	const signal = new AbortController().signal;
	let next = 10;
	const shared = capabilities({
		createCompositionSeed: () => next++,
		renderLayout: async (...args) => { calls.push(['layout', ...args]); return candidate('layout'); }
	});
	const layoutPlans = await planRefinementCandidates(input({ kind: 'layout', count: 2, signal }), shared);

	assert.deepEqual(layoutPlans.map((plan) => plan.label), ['Layout 1', 'Layout 2']);
	await Promise.all(layoutPlans.map((plan) => plan.run()));
	assert.deepEqual(calls, [
		['layout', 10, 'Layout 1', signal],
		['layout', 11, 'Layout 2', signal]
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
