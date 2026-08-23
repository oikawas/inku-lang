import type {
	RefineKind,
	VariationAmplitude,
	VariationCandidate
} from './refinement-session.svelte.ts';

export type RefinementCandidatePlan = {
	label: string;
	run: () => Promise<VariationCandidate>;
};

export type RefinementFanoutLabels = {
	touch: string;
	layout: string;
	reading: string;
	variation: string;
	color: string;
	noAlternateCatalog: string;
};

export type RefinementFanoutInput = {
	kind: RefineKind;
	count: 1 | 4;
	touchWords: string;
	amplitude?: VariationAmplitude;
	signal: AbortSignal;
	labels: RefinementFanoutLabels;
	currentCompositionSeed: number | null | undefined;
	previousCandidates: readonly VariationCandidate[];
	availableCatalogIds: readonly string[];
	currentCatalogId: string;
	random?: () => number;
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

function alternateCatalogIds(input: RefinementFanoutInput): string[] {
	const candidates = input.availableCatalogIds.filter((id) => id && id !== input.currentCatalogId);
	const random = input.random ?? Math.random;
	for (let index = candidates.length - 1; index > 0; index -= 1) {
		const swapIndex = Math.floor(random() * (index + 1));
		[candidates[index], candidates[swapIndex]] = [candidates[swapIndex], candidates[index]];
	}
	if (candidates.length === 0) throw new Error(input.labels.noAlternateCatalog);
	return Array.from({ length: input.count }, (_, index) => candidates[index % candidates.length]);
}

/** Build every label and factory before the first candidate request starts. */
export async function planRefinementCandidates(
	input: RefinementFanoutInput,
	capabilities: RefinementFanoutCapabilities
): Promise<RefinementCandidatePlan[]> {
	const usedCompositionSeeds = new Set<number>();
	if (Number.isFinite(input.currentCompositionSeed ?? NaN)) {
		usedCompositionSeeds.add(Number(input.currentCompositionSeed));
	}
	for (const candidate of input.previousCandidates) {
		if (Number.isFinite(candidate.result.composition_seed ?? NaN)) {
			usedCompositionSeeds.add(Number(candidate.result.composition_seed));
		}
	}

	// Refinement intentionally draws alternate catalogs. Reading the description
	// would choose once and collapse the author-selectable grid into one answer.
	const catalogIds = input.kind === 'color' ? alternateCatalogIds(input) : [];
	const resolvedAmplitude = input.amplitude ?? 'medium';
	// Allocate the complete seed sequence before planning jobs because the Server
	// owns variation numbering and candidate order follows the returned indexes.
	const variationSeeds = input.kind === 'variation'
		? await capabilities.allocateVariationSeeds(resolvedAmplitude, input.count)
		: [];

	return Array.from({ length: input.count }, (_, index) => {
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
		const label = `${input.labels.color} ${sequence} · ${capabilities.catalogName(catalogId)}`;
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
