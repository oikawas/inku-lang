/**
 * What the client asks for when a work leaves as one sheet.
 *
 * Kept apart from the download itself so the request body can be driven
 * directly: the seal and the page shape are chosen in the UI and honoured by
 * the server, and a card that always sends the same two constants would look
 * correct in the picture and be wrong in every other setting.
 */

export type CardLayout = 'square' | 'portrait';

export type CardExportSettings = {
	layout: CardLayout;
	seal: boolean;
};

export type CardExportRequestBody = {
	id: string;
	layout: CardLayout;
	seal: boolean;
};

// The seal is on by default. A card that carries no mark of where it came from
// is the honest option to offer, not the one to make people opt into.
export const DEFAULT_CARD_EXPORT_SETTINGS: CardExportSettings = {
	layout: 'square',
	seal: true
};

const LAYOUTS: CardLayout[] = ['square', 'portrait'];

export function normalizeCardExportSettings(value: unknown): CardExportSettings {
	const raw = value && typeof value === 'object' ? value as Partial<CardExportSettings> : {};
	return {
		layout: LAYOUTS.includes(raw.layout as CardLayout)
			? raw.layout as CardLayout
			: DEFAULT_CARD_EXPORT_SETTINGS.layout,
		// Only an explicit false turns the seal off, so a stored setting written
		// before this flag existed keeps the default rather than reading as off.
		seal: raw.seal === false ? false : DEFAULT_CARD_EXPORT_SETTINGS.seal
	};
}

export function parseCardExportSettings(value: string | null): CardExportSettings {
	if (!value) return { ...DEFAULT_CARD_EXPORT_SETTINGS };
	try {
		return normalizeCardExportSettings(JSON.parse(value));
	} catch {
		return { ...DEFAULT_CARD_EXPORT_SETTINGS };
	}
}

export function cardExportRequestBody(
	id: string,
	settings: CardExportSettings
): CardExportRequestBody {
	return { id, layout: settings.layout, seal: settings.seal };
}
