// Intentionally owned by the bridge. Do not import the independent experiment.
export const PROTOCOL = 'inku.ddl3d.v1';
export type ViewState = {
	position: [number, number, number]; target: [number, number, number]; zoom: number;
	projection: 'perspective' | 'orthographic'; depth: number; orthoHeight: number;
};
export function validViewState(value: unknown): value is ViewState {
	if (!value || typeof value !== 'object') return false;
	const v = value as ViewState;
	const vector = (a: number[]) => Array.isArray(a) && a.length === 3 && a.every(n => Number.isFinite(n) && Math.abs(n) < 10000);
	return vector(v.position) && vector(v.target) && Number.isFinite(v.zoom) && v.zoom >= 0.001 && v.zoom <= 1000
		&& (v.projection === 'perspective' || v.projection === 'orthographic') && v.depth >= 0.1 && v.depth <= 3
		&& Number.isFinite(v.orthoHeight) && v.orthoHeight > 0 && v.orthoHeight < 1000;
}
let previous: { inputJson: string; state: ViewState } | null = null;
export function remember(inputJson: string, state: ViewState) { previous = { inputJson, state }; }
export function recall(inputJson: string): ViewState | undefined { return previous?.inputJson === inputJson ? previous.state : undefined; }
