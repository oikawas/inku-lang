import type { Mesh } from 'three';
import type { MeshPacket } from '../scene/types.ts';
import { lineDepthAt } from '../scene/lineDepth.ts';

/** Capture after paint mapping, which can split a vertex between cap and wall. */
export function objectDepth(mesh: Mesh, packet: MeshPacket) {
  const positions = mesh.geometry.getAttribute('position');
  const original = new Float32Array(positions.count), offsets = new Float32Array(positions.count);
  // A tube ring's vertices repeat across caps and walls; search the centerline once per place.
  const known = new Map<string, number>();
  if (packet.depthPath) for (let i = 0; i < positions.count; i++) {
    original[i] = positions.getZ(i);
    const x = positions.getX(i), y = positions.getY(i), key = `${x} ${y}`;
    let offset = known.get(key);
    if (offset === undefined) { offset = lineDepthAt(packet.depthPath, x, y) - packet.layerZ; known.set(key, offset); }
    offsets[i] = offset;
  }
  return (thickness: number, spacing: number) => {
    mesh.position.z = packet.layerZ * spacing;
    mesh.scale.z = packet.depthPath ? 1 : thickness;
    if (!packet.depthPath) return;
    for (let i = 0; i < positions.count; i++) positions.setZ(i, original[i] * thickness + offsets[i] * spacing);
    positions.needsUpdate = true;
    mesh.geometry.computeVertexNormals(); mesh.geometry.computeBoundingBox(); mesh.geometry.computeBoundingSphere();
  };
}
