export type UiMode = 'simple' | 'full' | 'custom';

export const UI_VISIBILITY_KEYS = [
	'input_modes',
	'drawing_settings',
	'ddl_tools',
	'detail_status',
	'work_tools',
	'history',
	'auxiliary',
] as const;

export type UiVisibilityKey = (typeof UI_VISIBILITY_KEYS)[number];
export type UiCustomVisibility = Partial<Record<UiVisibilityKey, boolean>>;

export const SIMPLE_UI_VISIBILITY: Record<UiVisibilityKey, boolean> = {
	input_modes: false,
	drawing_settings: false,
	ddl_tools: false,
	detail_status: false,
	work_tools: false,
	history: false,
	auxiliary: false,
};

export const FULL_UI_VISIBILITY: Record<UiVisibilityKey, boolean> = {
	input_modes: true,
	drawing_settings: true,
	ddl_tools: true,
	detail_status: true,
	work_tools: true,
	history: true,
	auxiliary: true,
};

export function normalizeUiMode(value: unknown): UiMode {
	return value === 'full' || value === 'custom' ? value : 'simple';
}

export function normalizeUiCustom(value: unknown): UiCustomVisibility {
	if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
	const source = value as Record<string, unknown>;
	return Object.fromEntries(
		UI_VISIBILITY_KEYS.flatMap((key) => typeof source[key] === 'boolean' ? [[key, source[key]]] : []),
	) as UiCustomVisibility;
}

export function resolveUiVisibility(mode: UiMode, custom: UiCustomVisibility): Record<UiVisibilityKey, boolean> {
	if (mode === 'full') return FULL_UI_VISIBILITY;
	if (mode === 'simple') return SIMPLE_UI_VISIBILITY;
	return { ...SIMPLE_UI_VISIBILITY, ...custom };
}
