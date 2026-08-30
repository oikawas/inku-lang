// Sketch from life (Stage 0.5, v2.10). Single source for the values and labels.
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

// What the record says the layer did for one work. Five values, plus a sixth
// state the record can be in: no value at all, meaning the work was drawn
// before the record existed. That absence is NOT 'off' -- 'off' is a choice the
// author made, and the works that predate the column made no such choice.
export type SketchState = 'fine' | 'coarse' | 'fallback' | 'off' | 'not_applicable';
export const SKETCH_STATES: SketchState[] = ['fine', 'coarse', 'fallback', 'off', 'not_applicable'];

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

/** A note the menu shows beside an option. Off is kept -- the layer can still
 *  be skipped -- but it is not what the work should normally be drawn through,
 *  and the menu is the only place that says so: the compact toggle has no room
 *  and the lineage panel is reporting a past work, not offering a choice. */
export function sketchModeNote(mode: SketchMode, isJapanese: boolean): string {
	if (mode !== 'off') return '';
	return isJapanese ? '（推奨しない）' : '(not recommended)';
}

/** A work with no state recorded is not a work drawn with the layer off. */
export function normalizeSketchState(value: unknown): SketchState | null {
	return typeof value === 'string' && (SKETCH_STATES as string[]).includes(value)
		? (value as SketchState)
		: null;
}

/** What to tell the author about the work on screen. `null` means the record
 *  itself is absent -- the work predates the column -- and that reads
 *  differently from every recorded state, 'off' included. Rounding the two
 *  together here would undo the whole point of the column. */
export function sketchStateNote(state: SketchState | null, isJapanese: boolean): string {
	if (state === 'fine' || state === 'coarse') return '';
	// Written on one line each so `npm run lint:i18n` sees them: its ternary
	// pattern does not span lines, and a wrapped string is a string nobody reads.
	if (state === 'fallback') return isJapanese ? '写生を試みたが届かず、記述のまま解釈した' : 'The layer was tried, did not answer, and the description was read as it stood';
	if (state === 'off') return isJapanese ? '写生を通さずに描いた' : 'Drawn without the layer';
	if (state === 'not_applicable') return isJapanese ? 'この経路は写生を通らない' : 'This path does not go through the layer';
	return isJapanese ? '写生が記録される前に描かれた（切って描いたのではない）' : 'Drawn before the layer was recorded, which is not the same as off';
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
