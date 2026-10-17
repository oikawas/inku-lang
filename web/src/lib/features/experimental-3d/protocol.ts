// Intentionally owned by the bridge. Do not import the independent experiment.
export const PROTOCOL = 'inku.ddl3d.v1';
export type InitialView = { pixelWidth: number; pixelHeight: number; panX: number; panY: number; zoom: number };
export type ViewerCommand = { id: number; action: 'zoom' | 'reset'; value?: number };
export type ViewState = {
	position: [number, number, number]; target: [number, number, number]; zoom: number;
	projection: 'perspective' | 'orthographic'; depth: number; orthoHeight: number;
	layerSpacing?: number;
	background?: 'none' | 'support' | 'sky' | 'stars' | 'paint' | 'white' | 'black';
	referenceHeight?: number;
	displayZoom?: number;
};
export function validViewState(value: unknown): value is ViewState {
	if (!value || typeof value !== 'object') return false;
	const v = value as ViewState;
	const vector = (a: number[]) => Array.isArray(a) && a.length === 3 && a.every(n => Number.isFinite(n) && Math.abs(n) < 10000);
	return vector(v.position) && vector(v.target) && Number.isFinite(v.zoom) && v.zoom >= 0.001 && v.zoom <= 1000
		&& (v.projection === 'perspective' || v.projection === 'orthographic') && v.depth >= 0.1 && v.depth <= 3
		&& (v.layerSpacing === undefined || (Number.isFinite(v.layerSpacing) && v.layerSpacing >= 0 && v.layerSpacing <= 3))
		&& (v.background === undefined || ['none', 'support', 'sky', 'stars', 'paint', 'white', 'black'].includes(v.background))
		&& (v.referenceHeight === undefined || (Number.isFinite(v.referenceHeight) && v.referenceHeight > 0 && v.referenceHeight < 1000))
		&& (v.displayZoom === undefined || (Number.isFinite(v.displayZoom) && v.displayZoom > 0 && v.displayZoom <= 10000))
		&& Number.isFinite(v.orthoHeight) && v.orthoHeight > 0 && v.orthoHeight < 1000;
}
let previous: { inputJson: string; state: ViewState } | null = null;
export function remember(inputJson: string, state: ViewState) { previous = { inputJson, state }; }
export function recall(inputJson: string): ViewState | undefined { return previous?.inputJson === inputJson ? previous.state : undefined; }
