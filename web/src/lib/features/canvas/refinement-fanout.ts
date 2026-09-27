import type {
	RefineKind,
	VariationAmplitude,
	VariationCandidate
} from './refinement-session.svelte.ts';
import type { Seed } from '../run/current-work.ts';

export type RefinementCandidatePlan = {
	label: string;
	run: () => Promise<VariationCandidate>;
};

export type RefinementFanoutLabels = {
	touch: string;
	layout: string;
	reading: string;
	variation: string;
	noAlternateCatalog: string;
};

export type RefinementFanoutInput = {
	kind: RefineKind;
	/** Ignored for color: that plan offers every other catalog. */
	count: number;
	touchWords: string;
	amplitude?: VariationAmplitude;
	signal: AbortSignal;
	labels: RefinementFanoutLabels;
	currentCompositionSeed: Seed | null | undefined;
	previousCandidates: readonly VariationCandidate[];
	availableCatalogIds: readonly string[];
	currentCatalogId: string;
};

export type RefinementFanoutCapabilities = {
	createCompositionSeed(excluded: Set<number>): number;
	allocateVariationSeeds(amplitude: VariationAmplitude, count: number): Promise<number[]>;
	catalogName(id: string): string;
	renderTouch(words: string, label: string, signal: AbortSignal): Promise<VariationCandidate>;
	renderLayout(seed: number, label: string, signal: AbortSignal): Promise<VariationCandidate>;
	renderReading(label: string, signal: AbortSignal): Promise<VariationCandidate>;
	renderVariation(
		amplitude: VariationAmplitude,
		seed: number,
		label: string,
		signal: AbortSignal
	): Promise<VariationCandidate>;
	renderColor(catalogId: string, label: string, signal: AbortSignal): Promise<VariationCandidate>;
};

/** Every catalog but the one the work uses, in the catalog list's order. */
export function otherCatalogIds(availableCatalogIds: readonly string[], currentCatalogId: string): string[] {
	return availableCatalogIds.filter((id) => id && id !== currentCatalogId);
}

/** Build every label and factory before the first candidate request starts. */
export async function planRefinementCandidates(
	input: RefinementFanoutInput,
	capabilities: RefinementFanoutCapabilities
): Promise<RefinementCandidatePlan[]> {
	const usedCompositionSeeds = new Set<number>();
	// Seeds arrive as decimal strings, so read them as numbers before the
	// check; only avoiding a repeat depends on it, so rounding does no harm.
	for (const seed of [input.currentCompositionSeed, ...input.previousCandidates.map((candidate) => candidate.result.composition_seed)]) {
		const used = Number(seed ?? NaN);
		if (Number.isFinite(used)) usedCompositionSeeds.add(used);
	}

	// The color change shows the work in every other catalog side by side, so
	// the author compares them all instead of a random few.
	const catalogIds = input.kind === 'color' ? otherCatalogIds(input.availableCatalogIds, input.currentCatalogId) : [];
	if (input.kind === 'color' && catalogIds.length === 0) throw new Error(input.labels.noAlternateCatalog);
	const planCount = input.kind === 'color' ? catalogIds.length : input.count;
	const resolvedAmplitude = input.amplitude ?? 'medium';
	// Allocate the complete seed sequence before planning jobs because the Server
	// owns variation numbering and candidate order follows the returned indexes.
	const variationSeeds = input.kind === 'variation'
		? await capabilities.allocateVariationSeeds(resolvedAmplitude, input.count)
		: [];

	return Array.from({ length: planCount }, (_, index) => {
		const sequence = index + 1;
		if (input.kind === 'touch') {
			const label = input.labels.touch;
			return {
				label,
				run: () => capabilities.renderTouch(input.touchWords, label, input.signal)
			};
		}
		if (input.kind === 'layout') {
			const compositionSeed = capabilities.createCompositionSeed(usedCompositionSeeds);
			usedCompositionSeeds.add(compositionSeed);
			const label = `${input.labels.layout} ${sequence}`;
			return {
				label,
				run: () => capabilities.renderLayout(compositionSeed, label, input.signal)
			};
		}
		if (input.kind === 'reading') {
			const label = `${input.labels.reading} ${sequence}`;
			return {
				label,
				run: () => capabilities.renderReading(label, input.signal)
			};
		}
		if (input.kind === 'variation') {
			const label = `${input.labels.variation} ${sequence}`;
			return {
				label,
				run: () => capabilities.renderVariation(
					resolvedAmplitude,
					variationSeeds[index],
					label,
					input.signal
				)
			};
		}
		const catalogId = catalogIds[index];
		const label = capabilities.catalogName(catalogId);
		return {
			label,
			run: () => capabilities.renderColor(catalogId, label, input.signal)
		};
	});
}

export type RefinementFanoutHooks = {
	onStart?: (index: number) => void;
	onDone?: (index: number) => void;
};

/** Run indexed jobs within the resolved cap while retaining input-order results. */
export async function runRefinementFanout<T>(
	jobs: Array<() => Promise<T>>,
	limit: number,
	hooks?: RefinementFanoutHooks
): Promise<T[]> {
	const results = new Array<T>(jobs.length);
	let next = 0;
	const workers = Array.from({ length: Math.max(1, Math.min(limit, jobs.length)) }, async () => {
		for (let index = next++; index < jobs.length; index = next++) {
			// Index hooks identify the lane in flight; completion count alone cannot.
			hooks?.onStart?.(index);
			results[index] = await jobs[index]();
			hooks?.onDone?.(index);
		}
	});
	await Promise.all(workers);
	return results;
}
