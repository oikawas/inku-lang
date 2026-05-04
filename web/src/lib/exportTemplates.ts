export type ExportTemplate = {
	id: string;
	name: string;
	description: string;
	y_px: number;
};

export const DEFAULT_EXPORT_TEMPLATES: ExportTemplate[] = [
	{ id: 'png-1080', name: 'PNG 1080px', description: 'PNG / Y軸 1080px', y_px: 1080 },
	{ id: 'png-2160', name: 'PNG 2160px', description: 'PNG / Y軸 2160px', y_px: 2160 },
	{ id: 'png-4320', name: 'PNG 4320px', description: 'PNG / Y軸 4320px', y_px: 4320 },
];

function isLegacyDefaultTemplates(value: unknown): boolean {
	if (!Array.isArray(value) || value.length !== 2) return false;
	const [first, second] = value as Array<Partial<ExportTemplate>>;
	return first?.id === 'png-1024'
		&& first?.y_px === 1024
		&& second?.id === 'png-2048'
		&& second?.y_px === 2048;
}

export function normalizeExportTemplates(value: unknown): ExportTemplate[] {
	const source = Array.isArray(value) && !isLegacyDefaultTemplates(value) ? value : DEFAULT_EXPORT_TEMPLATES;
	const normalized: ExportTemplate[] = [];
	const seen = new Set<string>();
	for (const item of source) {
		if (!item || typeof item !== 'object') continue;
		const raw = item as Partial<ExportTemplate>;
		const id = typeof raw.id === 'string' && raw.id.trim()
			? raw.id.trim().slice(0, 80)
			: `png-${Math.random().toString(36).slice(2, 10)}`;
		if (seen.has(id)) continue;
		const name = typeof raw.name === 'string' && raw.name.trim()
			? raw.name.trim().slice(0, 80)
			: 'PNG';
		const description = typeof raw.description === 'string'
			? raw.description.trim().slice(0, 240)
			: '';
		const yPx = Math.round(Number(raw.y_px));
		if (!Number.isFinite(yPx) || yPx < 64 || yPx > 12000) continue;
		normalized.push({ id, name, description, y_px: yPx });
		seen.add(id);
		if (normalized.length >= 20) break;
	}
	return normalized.length > 0 ? normalized : DEFAULT_EXPORT_TEMPLATES;
}
