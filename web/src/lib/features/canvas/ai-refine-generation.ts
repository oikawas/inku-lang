// The seeds of an autonomous refinement generation drawn from its parent's DDL
// (a work its edited DDL holds). Only what the kind changes is drawn anew: the
// performance for a touch, the placement for a layout; color and variation keep
// both, and change the catalog or the variation instead.

type Seed = number | string;

export type GenerationSeeds = { renderSeed?: Seed; compositionSeed?: Seed };

export function ddlGenerationSeeds(
	kind: string,
	parent: { renderSeed: Seed | null; compositionSeed: Seed | null },
	fresh: () => number
): GenerationSeeds {
	const render = parent.renderSeed ?? undefined;
	// The renderer places a work by its composition seed, or by its render seed
	// when it has none, so that is the placement a touch keeps.
	const placement = parent.compositionSeed ?? parent.renderSeed ?? undefined;
	if (kind === 'touch_change') return { renderSeed: fresh(), compositionSeed: placement };
	if (kind === 'layout_change') return { renderSeed: render, compositionSeed: fresh() };
	return { renderSeed: render, compositionSeed: parent.compositionSeed ?? undefined };
}
