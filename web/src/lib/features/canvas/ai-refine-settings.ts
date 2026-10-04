// The autonomous refinement dialog opens with the choices the author made last
// time (author's request, 2026-09-28). Kept in this browser, like the export
// settings; the Vision model is not here -- it is an account setting already.
// The wild switch is not kept: it follows the work being refined.

export type AiRefineMode = 'random' | 'vision';

export type AiRefineSettings = {
	mode: AiRefineMode;
	generations: number;
	reading: boolean;
	color: boolean;
	layout: boolean;
	touch: boolean;
	direction: string;
};

export const DEFAULT_AI_REFINE_SETTINGS: AiRefineSettings = {
	mode: 'random',
	generations: 5,
	reading: true,
	color: true,
	layout: true,
	touch: true,
	direction: ''
};

const KEY = 'inku-ai-refine-settings';

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
	const flag = (key: keyof AiRefineSettings, fallback: boolean) => (typeof stored[key] === 'boolean' ? stored[key] as boolean : fallback);
	const generations = stored.generations;
	return {
		mode: stored.mode === 'vision' || stored.mode === 'random' ? stored.mode : d.mode,
		generations: Number.isInteger(generations) && (generations as number) >= 1 && (generations as number) <= 10 ? generations as number : d.generations,
		reading: flag('reading', d.reading),
		color: flag('color', d.color),
		layout: flag('layout', d.layout),
		touch: flag('touch', d.touch),
		direction: typeof stored.direction === 'string' ? stored.direction : d.direction
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
