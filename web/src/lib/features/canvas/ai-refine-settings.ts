// The autonomous refinement dialog opens with the choices the author made last
// time (author's request, 2026-09-28). Kept in this browser, like the export
// settings; the model is not here -- it is an account setting already.
// The wild switch is not kept: it follows the work being refined.
// Since the Server takes the runs (2026-10-21) the choices are the moves to take,
// which moves, and the direction the laws move is given. The generations kept
// before are read as the moves; the colour and layout elements and the Vision
// direction went with the browser's loop, and are dropped like any unknown field.

import { AUTONOMOUS_MOVES_DEFAULT, AUTONOMOUS_NOTE_LIMIT } from '../autonomous/runs.ts';

export type AiRefineSettings = {
	moves: number;
	laws: boolean;
	juxtaposition: boolean;
	note: string;
};

export const DEFAULT_AI_REFINE_SETTINGS: AiRefineSettings = {
	moves: AUTONOMOUS_MOVES_DEFAULT,
	laws: true,
	juxtaposition: true,
	note: ''
};

const KEY = 'inku-ai-refine-settings';

function movesOf(value: unknown): number | null {
	return Number.isInteger(value) && (value as number) >= 1 && (value as number) <= 10 ? value as number : null;
}

/** Whatever was stored, each field checked on its own; anything unreadable is the default. */
export function parseAiRefineSettings(raw: string | null): AiRefineSettings {
	let stored: Record<string, unknown> = {};
	try {
		const value = raw ? JSON.parse(raw) : null;
		if (value && typeof value === 'object' && !Array.isArray(value)) stored = value as Record<string, unknown>;
	} catch {
		/* a damaged entry reads as nothing stored */
	}
	const d = DEFAULT_AI_REFINE_SETTINGS;
	const flag = (key: 'laws' | 'juxtaposition') => (typeof stored[key] === 'boolean' ? stored[key] as boolean : d[key]);
	return {
		moves: movesOf(stored.moves) ?? movesOf(stored.generations) ?? d.moves,
		laws: flag('laws'),
		juxtaposition: flag('juxtaposition'),
		note: typeof stored.note === 'string' ? stored.note.slice(0, AUTONOMOUS_NOTE_LIMIT) : d.note
	};
}

export function loadAiRefineSettings(): AiRefineSettings {
	try {
		return parseAiRefineSettings(localStorage.getItem(KEY));
	} catch {
		return { ...DEFAULT_AI_REFINE_SETTINGS };
	}
}

export function saveAiRefineSettings(settings: AiRefineSettings): void {
	try {
		localStorage.setItem(KEY, JSON.stringify(settings));
	} catch {
		/* private mode / quota: the choices still apply while the dialog is open */
	}
}
