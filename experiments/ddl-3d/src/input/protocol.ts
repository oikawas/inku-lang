export const PROTOCOL = 'inku.ddl3d.v1';
export const MAX_INPUT_BYTES = 16 * 1024 * 1024;
export interface ViewState {
  position: [number, number, number]; target: [number, number, number]; zoom: number;
  projection: 'perspective' | 'orthographic'; depth: number; orthoHeight: number;
}
export interface LoadMessage {
  protocol: typeof PROTOCOL; type: 'load-work'; requestId: number; mountId: string;
  inputJson: string; locale: 'ja' | 'en'; theme: 'light' | 'dark'; viewState?: ViewState;
}
export function validState(value: unknown): value is ViewState {
  if (!value || typeof value !== 'object') return false;
  const v = value as ViewState;
  const vector = (a: number[]) => Array.isArray(a) && a.length === 3 && a.every(n => Number.isFinite(n) && Math.abs(n) < 10000);
  return vector(v.position) && vector(v.target) && Number.isFinite(v.zoom) && v.zoom >= 0.001 && v.zoom <= 1000
    && (v.projection === 'perspective' || v.projection === 'orthographic') && v.depth >= 0.1 && v.depth <= 3
    && Number.isFinite(v.orthoHeight) && v.orthoHeight > 0 && v.orthoHeight < 1000;
}
export function validLoad(value: unknown): value is LoadMessage {
  if (!value || typeof value !== 'object') return false;
  const v = value as LoadMessage;
  return v.protocol === PROTOCOL && v.type === 'load-work' && Number.isSafeInteger(v.requestId) && v.requestId > 0
    && typeof v.mountId === 'string' && v.mountId.length <= 128 && typeof v.inputJson === 'string'
    && new TextEncoder().encode(v.inputJson).byteLength <= MAX_INPUT_BYTES
    && (v.locale === 'ja' || v.locale === 'en') && (v.theme === 'light' || v.theme === 'dark')
    && (v.viewState === undefined || validState(v.viewState));
}
