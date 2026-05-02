export type ExportTemplate = {
	id: string;
	name: string;
	description: string;
	y_px: number;
};

export const DEFAULT_EXPORT_TEMPLATES: ExportTemplate[] = [
	{ id: 'png-1024', name: 'PNG 1024px', description: 'PNG / y-axis 1024px', y_px: 1024 },
	{ id: 'png-2048', name: 'PNG 2048px', description: 'PNG / y-axis 2048px', y_px: 2048 },
];

export function normalizeExportTemplates(value: unknown): ExportTemplate[] {
	const source = Array.isArray(value) ? value : DEFAULT_EXPORT_TEMPLATES;
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
