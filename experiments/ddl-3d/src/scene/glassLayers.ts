/** The fan of glass layers holds at most this many layers. */
export const MAX_GLASS_LAYERS = 8;
/** Glass behind the back layer. */
export const BACK_GLASS = 0.03;

export interface GlassLayerPlan {
  /** Layer of each Score instruction that has marks, from the back. */
  layerOf: Map<number, number>;
  /** One label per layer: its chunk's name, or null. */
  names: (string | null)[];
  /** How the layers were found. */
  source: 'chunks' | 'instructions';
}

/**
 * Layers in paint order. With chunk names, a new layer starts where the name
 * changes, so a chunk named again after another one is a second layer and the
 * 2D overlap order holds. Without names, or when the chunks give one layer,
 * each instruction is a layer. More than `limit` layers merge neighbours.
 */
export function glassLayerPlan(sourceIndices: readonly number[], chunks: readonly (string | null)[] | null | undefined,
  limit = MAX_GLASS_LAYERS): GlassLayerPlan {
  const ordered = [...new Set(sourceIndices)].sort((a, b) => a - b);
  const runs = (key: (index: number) => string | null) => {
    const result: { name: string | null; members: number[] }[] = [];
    let previous: string | null | undefined;
    for (const index of ordered) {
      const name = key(index);
      if (!result.length || name !== previous) result.push({ name, members: [] });
      result[result.length - 1].members.push(index);
      previous = name;
    }
    return result;
  };
  let source: GlassLayerPlan['source'] = 'chunks';
  let layers = chunks && chunks.length ? runs(index => chunks[index] ?? null) : [];
  if (layers.length <= 1) {
    source = 'instructions';
    // A unique key per instruction; the names shown stay the chunk's.
    layers = runs(index => `#${index}`).map(run => ({ name: chunks?.[run.members[0]] ?? null, members: run.members }));
  }
  if (layers.length > limit) {
    const merged: typeof layers = [];
    for (let k = 0; k < limit; k++) {
      const part = layers.slice(Math.floor(k * layers.length / limit), Math.floor((k + 1) * layers.length / limit));
      merged.push({ name: part[0].name, members: part.flatMap(run => run.members) });
    }
    layers = merged;
  }
  const layerOf = new Map<number, number>();
  layers.forEach((run, layer) => run.members.forEach(index => layerOf.set(index, layer)));
  return { layerOf, names: layers.map(run => run.name), source };
}
