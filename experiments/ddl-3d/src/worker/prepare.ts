import { buildScene } from '../scene/build';
import type { PreparedScene } from '../scene/types';
import { MAX_INPUT_BYTES } from '../input/protocol';

self.onmessage = async (event: MessageEvent<{ inputJson: string; wasmUrl: string }>) => {
  try {
    const { inputJson, wasmUrl } = event.data;
    if (typeof inputJson !== 'string' || new TextEncoder().encode(inputJson).byteLength > MAX_INPUT_BYTES) throw new Error('input_budget_exceeded');
    const url = new URL(wasmUrl);
    if (url.origin !== self.location.origin || !url.pathname.endsWith('/wasm/score_adapter.js')) throw new Error('invalid_wasm_url');
    const adapter = await import(/* @vite-ignore */ url.href);
    await adapter.default();
    const input = JSON.parse(adapter.prepare_scene(inputJson)) as PreparedScene | { ok: false; error: string };
    if (!input.ok) throw new Error(input.error);
    const packet = buildScene(input);
    const buffers: ArrayBuffer[] = [];
    for (const mesh of packet.meshes) {
      buffers.push(mesh.positions.buffer as ArrayBuffer, mesh.normals.buffer as ArrayBuffer);
      if (mesh.indices) buffers.push(mesh.indices.buffer as ArrayBuffer);
    }
    (self as unknown as Worker).postMessage({ ok: true, packet }, buffers);
  } catch (error) {
    self.postMessage({ ok: false, error: error instanceof Error ? error.message : 'preparation_failed' });
  }
};
