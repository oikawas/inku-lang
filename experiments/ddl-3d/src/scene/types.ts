export type XY = [number, number];
export type Shape = { kind: 'round'; center: XY; radii: XY }
  | { kind: 'contour' | 'path'; points: XY[] };
export interface PaintAppearance {
  svg: string; bounds: [number, number, number, number]; center: XY;
}
export interface GeometryMark {
  sourceIndex: number; performedIndex: number; instanceIndex: number;
  primitive: string; shape: Shape; transform: [number, number, number, number, number, number];
  color: string; width: number; filled: boolean; opacity: number; dash: number[]; weight: string;
  clips: XY[][];
  pairFill?: { points: XY[]; sourceIndex: number; color: string; opacity: number; performedIndex?: number; instanceIndex?: number; appearance?: PaintAppearance } | null;
  appearance?: PaintAppearance;
}
export interface GeometryRecovery {
  kind: 'resource_omitted' | 'relation_omitted' | 'execution';
  instruction_index?: number; anchor_index?: number;
  disposition?: 'stopped' | 'omitted' | 'relation_omitted';
  reason?: string;
}
export interface GeometryScene { canvas: XY; background: string; ground: boolean; presenceSvg?: string; marks: GeometryMark[]; diagnostics: string[]; recoveries: GeometryRecovery[] }
export interface PreparedScene {
  ok: true; scene: GeometryScene;
  /** The chunk name of each Score instruction, when the saved DDL compiles to it. */
  chunks?: (string | null)[] | null; chunkSource?: 'ddl' | 'no_ddl' | 'ddl_mismatch';
  inputDigest: string; schemaDigest: string; mappingVersion: string; engineVersion: number;
}
export interface MeshPacket {
  positions: Float32Array; normals: Float32Array; indices: Uint32Array | null;
  color: string; opacity: number; sourceIndex: number; performedIndex: number; instanceIndex: number;
  primitive: string; role: 'object' | 'pair-fill'; relatedSourceIndex?: number;
  relatedPerformedIndex?: number; relatedInstanceIndex?: number; filled?: boolean;
  layerIndex: number; layerZ: number;
  depthPath?: { points: XY[]; depths: number[] };
  /** A painted path's tube: per vertex its ring's centre (x, y) and unit tangent (x, y), on the canvas plane. */
  axis?: Float32Array;
  /** How far a filled square that covers much of the canvas has thinned to a board (0..1). */
  board?: number;
  /** An unfilled round's outline on the canvas plane (x, y pairs), for the glass's footprint. */
  outline?: Float32Array;
  appearance?: PaintAppearance;
}
export interface ScenePacket {
  presenceSvg?: string;
  meshes: MeshPacket[]; canvas: XY; background: string; ground: boolean; diagnostics: string[];
  recoveries: GeometryRecovery[];
  objectCount: number; triangles: number; bytes: number; clippedObjects: number; layerCount: number;
  emptyPaths: { sourceIndex: number; performedIndex: number; instanceIndex: number }[];
  inputDigest: string; schemaDigest: string; mappingVersion: string; engineVersion: number;
  chunks?: (string | null)[] | null; chunkSource?: 'ddl' | 'no_ddl' | 'ddl_mismatch';
}
