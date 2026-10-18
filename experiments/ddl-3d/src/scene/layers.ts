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
  // Divide the full depth range between individual objects, including copies.
  // Keep source layers ordered and reverse the order within each layer.
  const shortSide = Math.min(...canvas), span = shortSide * 0.8;
  const starts = new Map<number, number>();
  let count = 0;
  for (const [index, layer] of members) { starts.set(index, count); count += layer.size; }
  for (const mesh of meshes) {
    const layer = members.get(mesh.layerIndex)!;
    const index = starts.get(mesh.layerIndex)! + layer.size - 1 - layer.get(unitRoot(key(mesh)))!;
    mesh.layerZ = count > 1 ? (index / (count - 1) - 0.5) * span : 0;
  }
  return ranks.size;
}
