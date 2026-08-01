export type AnimationExportFormat = 'apng' | 'gif';
export type AnimationPattern = 'cut' | 'crossfade' | 'fade_white' | 'slide';
export type AnimationResolution = '150' | '300' | '500' | '1k' | '4k' | '8k' | 'custom';

export type AnimationExportSettings = {
	format: AnimationExportFormat;
	pattern: AnimationPattern;
	holdSeconds: number;
	resolution: AnimationResolution;
	customHeight: number;
};

export const DEFAULT_ANIMATION_EXPORT_SETTINGS: AnimationExportSettings = {
	format: 'apng',
	pattern: 'crossfade',
	holdSeconds: 1.5,
	resolution: '1k',
	customHeight: 720
};

const FORMATS: AnimationExportFormat[] = ['apng', 'gif'];
const PATTERNS: AnimationPattern[] = ['cut', 'crossfade', 'fade_white', 'slide'];
const RESOLUTIONS: AnimationResolution[] = ['150', '300', '500', '1k', '4k', '8k', 'custom'];
const MIN_ANIMATION_HEIGHT = 64;
const MAX_ANIMATION_HEIGHT = 12000;
const RESOLUTION_HEIGHTS: Record<Exclude<AnimationResolution, 'custom'>, number> = {
	'150': 150,
	'300': 300,
	'500': 500,
	'1k': 1080,
	'4k': 2160,
	'8k': 4320
};

export function normalizeAnimationExportSettings(value: unknown): AnimationExportSettings {
	const raw = value && typeof value === 'object' ? value as Partial<AnimationExportSettings> : {};
	const holdSeconds = Number(raw.holdSeconds);
	const customHeight = Number(raw.customHeight);
	return {
		format: FORMATS.includes(raw.format as AnimationExportFormat) ? raw.format as AnimationExportFormat : DEFAULT_ANIMATION_EXPORT_SETTINGS.format,
		pattern: PATTERNS.includes(raw.pattern as AnimationPattern) ? raw.pattern as AnimationPattern : DEFAULT_ANIMATION_EXPORT_SETTINGS.pattern,
		holdSeconds: Number.isFinite(holdSeconds) ? Math.max(0.1, Math.min(30, holdSeconds)) : DEFAULT_ANIMATION_EXPORT_SETTINGS.holdSeconds,
		resolution: RESOLUTIONS.includes(raw.resolution as AnimationResolution) ? raw.resolution as AnimationResolution : DEFAULT_ANIMATION_EXPORT_SETTINGS.resolution,
		customHeight: Number.isFinite(customHeight)
			? Math.max(MIN_ANIMATION_HEIGHT, Math.min(MAX_ANIMATION_HEIGHT, Math.round(customHeight)))
			: DEFAULT_ANIMATION_EXPORT_SETTINGS.customHeight
	};
}

export function parseAnimationExportSettings(value: string | null): AnimationExportSettings {
	if (!value) return { ...DEFAULT_ANIMATION_EXPORT_SETTINGS };
	try {
		return normalizeAnimationExportSettings(JSON.parse(value));
	} catch {
		return { ...DEFAULT_ANIMATION_EXPORT_SETTINGS };
	}
}

type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>;

function filenameFromResponse(response: Response, format: AnimationExportFormat): string {
	const disposition = response.headers.get('content-disposition') ?? '';
	const match = disposition.match(/filename="([^"]+)"/i);
	if (match?.[1]) return match[1];
	const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\..+/, '');
	return `inku-animation-${stamp}.${format === 'apng' ? 'png' : 'gif'}`;
}

export async function downloadAnimation(
	apiFetch: ApiFetch,
	ids: string[],
	settings: AnimationExportSettings
): Promise<void> {
	const heightPx = settings.resolution === 'custom'
		? settings.customHeight
		: RESOLUTION_HEIGHTS[settings.resolution];
	const response = await apiFetch('/api/history/export-animation', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			ids,
			format: settings.format,
			pattern: settings.pattern,
			hold_seconds: settings.holdSeconds,
			resolution: ['1k', '4k', '8k'].includes(settings.resolution) ? settings.resolution : '1k',
			height_px: heightPx
		})
	});
	if (!response.ok) {
		const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
		throw new Error(typeof payload?.detail === 'string' ? payload.detail : `HTTP ${response.status}`);
	}
	const blob = await response.blob();
	const url = URL.createObjectURL(blob);
	try {
		const anchor = document.createElement('a');
		anchor.href = url;
		anchor.download = filenameFromResponse(response, settings.format);
		anchor.click();
	} finally {
		URL.revokeObjectURL(url);
	}
}
