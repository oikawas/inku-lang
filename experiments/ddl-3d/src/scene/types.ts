export type XY = [number, number];
export type Shape = { kind: 'round'; center: XY; radii: XY }
  | { kind: 'contour' | 'path'; points: XY[] };
export interface GeometryMark {
  sourceIndex: number; performedIndex: number; instanceIndex: number;
  primitive: string; shape: Shape; transform: [number, number, number, number, number, number];
  color: string; width: number; filled: boolean; opacity: number; dash: number[]; weight: string;
  clips: XY[][];
  pairFill?: { points: XY[]; sourceIndex: number; color: string; opacity: number } | null;
}
export interface GeometryRecovery {
  kind: 'resource_omitted' | 'relation_omitted' | 'execution';
  instruction_index?: number; anchor_index?: number;
  disposition?: 'stopped' | 'omitted' | 'relation_omitted';
  reason?: string;
}
export interface GeometryScene { canvas: XY; background: string; ground: boolean; marks: GeometryMark[]; diagnostics: string[]; recoveries: GeometryRecovery[] }
export interface PreparedScene {
  ok: true; scene: GeometryScene; inputDigest: string; schemaDigest: string; mappingVersion: string; engineVersion: number;
}
export interface MeshPacket {
  positions: Float32Array; normals: Float32Array; indices: Uint32Array | null;
  color: string; opacity: number; sourceIndex: number; performedIndex: number; instanceIndex: number;
  primitive: string; role: 'object' | 'pair-fill'; relatedSourceIndex?: number;
  layerIndex: number; layerZ: number;
}
export interface ScenePacket {
  meshes: MeshPacket[]; canvas: XY; background: string; ground: boolean; diagnostics: string[];
  recoveries: GeometryRecovery[];
  objectCount: number; triangles: number; bytes: number; clippedObjects: number; layerCount: number;
  inputDigest: string; schemaDigest: string; mappingVersion: string; engineVersion: number;
}
