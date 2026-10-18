import type { Mesh } from 'three';
import type { MeshPacket } from '../scene/types.ts';
import { lineDepthAt } from '../scene/lineDepth.ts';

/** Capture after paint mapping, which can expand indexed geometry vertices. */
export function objectDepth(mesh: Mesh, packet: MeshPacket) {
  const positions = mesh.geometry.getAttribute('position');
  const original = new Float32Array(positions.count), offsets = new Float32Array(positions.count);
  if (packet.depthPath) for (let i = 0; i < positions.count; i++) {
    original[i] = positions.getZ(i);
    offsets[i] = lineDepthAt(packet.depthPath, positions.getX(i), positions.getY(i)) - packet.layerZ;
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
