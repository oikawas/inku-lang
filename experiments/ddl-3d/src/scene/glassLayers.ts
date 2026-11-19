import type { XY } from './types.ts';

/** The fan of glass layers holds at most this many layers. */
export const MAX_GLASS_LAYERS = 8;
/** "Plane angle" 1 opens the front layer by this many degrees. */
export const FAN_DEGREES_PER_UNIT = 24;
/** "Layer depth" 1 parts neighbouring layers by this much at the axis. */
export const SPACING_PER_UNIT = 0.02;
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

export interface FanOptions {
  /** "Plane angle", 0 to 2. */ angle: number;
  /** "Layer depth", 0 to 3. */ spacing: number;
  /** Front glass thickness in short-side units. */ front: number;
  /** Back face tilt in degrees, 0 to 30. */ backTilt: number;
}

/** A plane z = offset + (x - axisX) * tan, after the block is centred. */
export interface FanPlane { tan: number; offset: number }

export interface FanGeometry {
  axisX: number;
  /** Fan layers from the back. */
  planes: FanPlane[];
  /** The back face: z = backOffset - (x - axisX) * backTan. */
  backOffset: number; backTan: number;
  front: number;
  /** Subtracted from every z so the block's centre is at z = 0. */
  shift: number;
}

/** The regular fan: equal angle steps about the paper's left edge. One layer
 * tilts by half the angle. Layers never cross inside the paper. */
export function fanGeometry(count: number, canvas: XY, options: FanOptions): FanGeometry {
  const [width] = canvas, axisX = -width / 2;
  const total = options.angle * FAN_DEGREES_PER_UNIT * Math.PI / 180;
  const spacing = options.spacing * SPACING_PER_UNIT;
  const angles = count <= 1 ? [total / 2] : Array.from({ length: count }, (_, i) => i * total / (count - 1));
  const raw = angles.map((angle, i) => ({ tan: Math.tan(angle), offset: i * spacing }));
  const frontMost = Math.max(...raw.map(plane => plane.offset + width * plane.tan));
  const backTan = Math.tan(options.backTilt * Math.PI / 180);
  const back = -BACK_GLASS, front = frontMost + options.front;
  // Centre the block between its front face and the deepest point of its back.
  const shift = (front + back - width * backTan) / 2;
  return {
    axisX, planes: raw.map(plane => ({ tan: plane.tan, offset: plane.offset - shift })),
    backOffset: back - shift, backTan, front: front - shift, shift,
  };
}

/** The depth of a fan plane at x. */
export function planeZ(plane: FanPlane, axisX: number, x: number): number {
  return plane.offset + (x - axisX) * plane.tan;
}
