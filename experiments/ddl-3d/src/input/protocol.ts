export const PROTOCOL = 'inku.ddl3d.v1';
export const MAX_INPUT_BYTES = 16 * 1024 * 1024;
export interface InitialView { pixelWidth: number; pixelHeight: number; panX: number; panY: number; zoom: number }
export interface ViewState {
  position: [number, number, number]; target: [number, number, number]; zoom: number;
  projection: 'perspective' | 'orthographic'; depth: number; orthoHeight: number;
  layerSpacing?: number;
  background?: 'none' | 'support' | 'sky' | 'stars';
  referenceHeight?: number;
  displayZoom?: number;
}
export interface LoadMessage {
  protocol: typeof PROTOCOL; type: 'load-work'; requestId: number; mountId: string;
  inputJson: string; locale: 'ja' | 'en'; theme: 'light' | 'dark'; viewState?: ViewState;
  initialView?: InitialView;
}
export function validState(value: unknown): value is ViewState {
  if (!value || typeof value !== 'object') return false;
  const v = value as ViewState;
  const vector = (a: number[]) => Array.isArray(a) && a.length === 3 && a.every(n => Number.isFinite(n) && Math.abs(n) < 10000);
  return vector(v.position) && vector(v.target) && Number.isFinite(v.zoom) && v.zoom >= 0.001 && v.zoom <= 1000
    && (v.projection === 'perspective' || v.projection === 'orthographic') && v.depth >= 0.1 && v.depth <= 3
    && (v.layerSpacing === undefined || (Number.isFinite(v.layerSpacing) && v.layerSpacing >= 0 && v.layerSpacing <= 3))
    && (v.background === undefined || ['none', 'support', 'sky', 'stars'].includes(v.background))
    && (v.referenceHeight === undefined || (Number.isFinite(v.referenceHeight) && v.referenceHeight > 0 && v.referenceHeight < 1000))
    && (v.displayZoom === undefined || (Number.isFinite(v.displayZoom) && v.displayZoom > 0 && v.displayZoom <= 10000))
    && Number.isFinite(v.orthoHeight) && v.orthoHeight > 0 && v.orthoHeight < 1000;
}
export function validLoad(value: unknown): value is LoadMessage {
  if (!value || typeof value !== 'object') return false;
  const v = value as LoadMessage;
  return v.protocol === PROTOCOL && v.type === 'load-work' && Number.isSafeInteger(v.requestId) && v.requestId > 0
    && typeof v.mountId === 'string' && v.mountId.length <= 128 && typeof v.inputJson === 'string'
    && new TextEncoder().encode(v.inputJson).byteLength <= MAX_INPUT_BYTES
    && (v.locale === 'ja' || v.locale === 'en') && (v.theme === 'light' || v.theme === 'dark')
    && (v.viewState === undefined || validState(v.viewState))
    && (v.initialView === undefined || validInitialView(v.initialView));
}
export function validInitialView(v: InitialView): boolean {
  return !!v && [v.pixelWidth, v.pixelHeight, v.zoom].every(n => Number.isFinite(n) && n > 0 && n < 100000)
    && [v.panX, v.panY].every(n => Number.isFinite(n) && Math.abs(n) < 100000);
}
