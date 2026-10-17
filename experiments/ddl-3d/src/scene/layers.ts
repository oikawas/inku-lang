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
  // Bound the total span, so a dense drawing does not become an enormous stack.
  const span = Math.min(...canvas) * 0.8;
  for (const mesh of meshes) mesh.layerZ = ranks.size > 1 ? (mesh.layerIndex / (ranks.size - 1) - 0.5) * span : 0;
  return ranks.size;
}
