// Sketch from life. Single source for the values and labels.
//
// The sketch runs before interpretation and never replaces the description: it
// supplements the extent of place and the seasonal or time-of-day light that
// the description leaves unstated. Three choices:
//   auto   -- supplement only when the description lacks cues to draw from
//   off    -- no sketch; the description alone is interpreted
//   always -- supplement even when the description states its cues (the
//             author's "draw again with a sketch")
// No choice waits for a confirmation; the drawing always runs to the end.
//
// English: the layer is "Sketch from life" and the short form "Sketch" is never
// used alone (author decision 2026-08-03) -- in the Stage 1 vocabulary "sketch"
// already means a pale pencil weight.
//
// Works saved before the supplement sketch recorded a grain (fine / coarse):
// the retired layer rewrote the description at that grain.
export type SketchGrain = 'fine' | 'coarse';
export type SketchMode = 'auto' | 'off' | 'always';

// What the record says the layer did for one work, plus a further state the
// record can be in: no value at all, meaning the work was drawn before the
// record existed. That absence is NOT 'off' -- 'off' is a choice the author
// made, and the works that predate the column made no such choice.
// 'supplemented' means the sketch added place or light beside the description;
// 'not_needed' means it judged the description's own cues sufficient.
export type SketchState = 'fine' | 'coarse' | 'fallback' | 'off' | 'not_applicable' | 'not_needed' | 'supplemented';
export const SKETCH_STATES: SketchState[] = ['fine', 'coarse', 'fallback', 'off', 'not_applicable', 'not_needed', 'supplemented'];

export const SKETCH_MODES: SketchMode[] = ['auto', 'off', 'always'];
export const SKETCH_GRAINS: SketchGrain[] = ['fine', 'coarse'];

// The author's default: the sketch supplements only when it is needed.
export const DEFAULT_SKETCH_MODE: SketchMode = 'auto';
export const DEFAULT_SKETCH_GRAIN: SketchGrain = 'fine';

export function sketchModeLabel(mode: SketchMode, isJapanese: boolean): string {
	if (mode === 'off') return isJapanese ? 'なし' : 'Off';
	if (mode === 'always') return isJapanese ? 'あり' : 'Always';
	return isJapanese ? '自動' : 'Auto';
}

export function sketchModeHint(mode: SketchMode, isJapanese: boolean): string {
	if (mode === 'off') {
		return isJapanese
			? '写生を通さず、記述だけで描く'
			: 'Skip the layer and draw from the description alone';
	}
	if (mode === 'always') {
		return isJapanese
			? '記述に手掛かりがあっても、場所の広がりや季節・時刻の光を補って描く'
			: 'Supplement the extent of place and the seasonal or time-of-day light even when the description states them';
	}
	return isJapanese
		? '記述に描く手掛かりが足りないときだけ、場所の広がりや季節・時刻の光を補う'
		: 'Supplement the extent of place or the seasonal or time-of-day light only when the description lacks cues to draw from';
}

/** A note the menu shows beside an option. No choice is discouraged now. */
export function sketchModeNote(_mode: SketchMode, _isJapanese: boolean): string {
	return '';
}

/** The label of a grain a work saved before the supplement sketch recorded. */
export function sketchGrainLabel(grain: SketchGrain, isJapanese: boolean): string {
	if (grain === 'coarse') return isJapanese ? '大きく' : 'Coarse';
	return isJapanese ? '細かく' : 'Fine';
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
	if (state === 'supplemented') return isJapanese ? '記述に足りない場所の広がりや季節・時刻の光を補って描いた' : 'The layer supplemented the extent of place or the seasonal or time-of-day light the description left out';
	if (state === 'not_needed') return isJapanese ? '記述に描く手掛かりが足りていたので、写生は補わなかった' : 'The description gave enough cues to draw from, so the layer added nothing';
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

/** A mode read back from a saved choice. Batch conditions saved before the
 *  supplement sketch hold a grain: the layer was on, which is now 'auto'. */
export function sketchModeOf(value: unknown): SketchMode {
	if (value === 'auto' || value === 'off' || value === 'always') return value;
	return normalizeSketchGrain(value) ? 'auto' : 'off';
}
