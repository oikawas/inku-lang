// The seeds of an autonomous refinement generation drawn from its parent's DDL
// (a work its edited DDL holds). Only what the kind changes is drawn anew: the
// placement for a layout; color keeps both seeds and changes the catalog instead.

type Seed = number | string;

export type GenerationSeeds = { renderSeed?: Seed; compositionSeed?: Seed };

export function ddlGenerationSeeds(
	kind: string,
	parent: { renderSeed: Seed | null; compositionSeed: Seed | null },
	fresh: () => number
): GenerationSeeds {
	const render = parent.renderSeed ?? undefined;
	if (kind === 'layout_change') return { renderSeed: render, compositionSeed: fresh() };
	return { renderSeed: render, compositionSeed: parent.compositionSeed ?? undefined };
}
