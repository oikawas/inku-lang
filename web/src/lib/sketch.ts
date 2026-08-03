// 写生 (Stage 0.5, v2.10). Single source for the values and labels.
//
// The layer rewrites the description as prose in the language of things before
// Stage 1 reads it. One control carries three states: off (the plain path, the
// description goes straight to Stage 1), fine and coarse. Fine and coarse do
// not change how much is said -- only how big the pieces are. Cut fine, the
// number of instructions grows; cut coarse, each instruction carries more.
//
// English: the layer is "Sketch from life" and the short form "Sketch" is never
// used alone (author decision 2026-08-03) -- in the Stage 1 vocabulary "sketch"
// already means a pale pencil weight.
export type SketchGrain = 'fine' | 'coarse';
export type SketchMode = 'off' | SketchGrain;

export const SKETCH_MODES: SketchMode[] = ['off', 'fine', 'coarse'];
export const SKETCH_GRAINS: SketchGrain[] = ['fine', 'coarse'];

// The author's default: the layer runs, cutting fine.
export const DEFAULT_SKETCH_MODE: SketchMode = 'fine';
export const DEFAULT_SKETCH_GRAIN: SketchGrain = 'fine';

export function sketchModeLabel(mode: SketchMode, isJapanese: boolean): string {
	if (mode === 'off') return isJapanese ? '切' : 'Off';
	if (mode === 'fine') return isJapanese ? '細かく' : 'Fine';
	return isJapanese ? '大きく' : 'Coarse';
}

export function sketchModeHint(mode: SketchMode, isJapanese: boolean): string {
	if (mode === 'off') {
		return isJapanese
			? '写生を通さず、記述をそのまま解釈へ渡す'
			: 'Skip the layer and send the description straight to interpretation';
	}
	if (mode === 'fine') {
		return isJapanese
			? '細かく区切って解釈する。一文に一つのことを書く'
			: 'Cut fine: one fact per short sentence, so more instructions come out';
	}
	return isJapanese
		? '大きく区切って深く解釈する。関係のあることを一文に束ねる'
		: 'Cut coarse: related facts bundled into longer sentences, each read more deeply';
}

// Works saved before v2.10 have no grain recorded.
export function normalizeSketchGrain(value: unknown): SketchGrain | null {
	return value === 'fine' || value === 'coarse' ? value : null;
}

export function sketchGrainOf(mode: SketchMode): SketchGrain | null {
	return mode === 'off' ? null : mode;
}

export function sketchModeOf(grain: unknown): SketchMode {
	return normalizeSketchGrain(grain) ?? 'off';
}
