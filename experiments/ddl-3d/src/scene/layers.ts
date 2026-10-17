import type { MeshPacket, XY } from './types.ts';

/** Use the core's paint order, keeping copies and closed arc pairs together. */
export function assignLayers(meshes: MeshPacket[], canvas: XY): number {
  const parents = new Map(meshes.map(mesh => [mesh.sourceIndex, mesh.sourceIndex]));
  const root = (id: number): number => {
    let current = id;
    while (parents.has(current) && parents.get(current) !== current) current = parents.get(current)!;
    return current;
  };
  for (const mesh of meshes) {
    if (mesh.role === 'pair-fill' && mesh.relatedSourceIndex !== undefined && parents.has(mesh.relatedSourceIndex)) {
      parents.set(root(mesh.relatedSourceIndex), root(mesh.sourceIndex));
    }
  }
  const ranks = new Map<number, number>();
  for (const mesh of meshes) {
    const id = root(mesh.sourceIndex);
    if (!ranks.has(id)) ranks.set(id, ranks.size);
    mesh.layerIndex = ranks.get(id)!;
  }
  const key = (mesh: MeshPacket) => `${mesh.performedIndex}:${mesh.instanceIndex}`;
  const units = new Map(meshes.map(mesh => [key(mesh), key(mesh)]));
  const unitRoot = (id: string): string => {
    while (units.has(id) && units.get(id) !== id) id = units.get(id)!;
    return id;
  };
  for (const mesh of meshes) {
    if (mesh.role !== 'pair-fill' || mesh.relatedPerformedIndex === undefined) continue;
    const other = `${mesh.relatedPerformedIndex}:${mesh.relatedInstanceIndex ?? 0}`;
    if (units.has(other)) units.set(unitRoot(other), unitRoot(key(mesh)));
  }
  const members = new Map<number, Map<string, number>>();
  for (const mesh of meshes) {
    let layer = members.get(mesh.layerIndex);
    if (!layer) { layer = new Map(); members.set(mesh.layerIndex, layer); }
    const unit = unitRoot(key(mesh));
    if (!layer.has(unit)) layer.set(unit, layer.size);
  }
  // Later objects recede by at most one source pixel per step. A dense layer
  // cannot use more than 2% of the canvas or a quarter of the layer gap.
  const shortSide = Math.min(...canvas), span = shortSide * 0.8;
  const gap = ranks.size > 1 ? span / (ranks.size - 1) : span;
  for (const mesh of meshes) {
    const layer = members.get(mesh.layerIndex)!;
    const step = Math.min(shortSide * 0.001, Math.min(shortSide * 0.02, gap / 4) / Math.max(1, layer.size - 1));
    const base = ranks.size > 1 ? (mesh.layerIndex / (ranks.size - 1) - 0.5) * span : 0;
    mesh.layerZ = base - layer.get(unitRoot(key(mesh)))! * step;
  }
  return ranks.size;
}
