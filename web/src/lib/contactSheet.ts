// Contact sheet: lay selected artworks out on one sheet and rasterise it to PNG.
// Each artwork is drawn separately into the canvas, so ids that repeat across
// SVG documents (texture filters, clip paths) can never collide.

export type ContactSheetEntry = {
	svg: string;
	caption: string;
	sub: string;
};

// 'review' is the sheet a person reads. 'ai' is sized for a vision model: the
// grid is squarer and the sheet is emitted at the long edge those models
// downscale to, so no budget is spent on pixels that get thrown away. Captions
// would be illegible after that downscale, so cells carry a number badge only
// and the descriptions belong in the prompt text instead.
export type SheetVariant = 'review' | 'ai';

type SheetLayout = {
	cols: number;
	rows: number;
	cellW: number;
	cellH: number;
	captionH: number;
	gap: number;
	pad: number;
	headerH: number;
	badge: boolean;
	targetLongEdge: number | null;
};

const LAYOUTS: Record<SheetVariant, SheetLayout> = {
	review: { cols: 7, rows: 4, cellW: 300, cellH: 220, captionH: 44, gap: 18, pad: 32, headerH: 58, badge: false, targetLongEdge: null },
	ai: { cols: 3, rows: 4, cellW: 300, cellH: 220, captionH: 0, gap: 14, pad: 24, headerH: 40, badge: true, targetLongEdge: 1568 }
};

const MAX_PIXEL_SIDE = 6000;
const FONT_STACK = 'system-ui, -apple-system, "Hiragino Sans", "Noto Sans JP", sans-serif';

export type ContactSheetOptions = {
	variant: SheetVariant;
	title: string;
	subtitle: string;
	// Caption numbering continues across the split sheets.
	startIndex?: number;
};

export function sheetCapacity(variant: SheetVariant): number {
	const layout = LAYOUTS[variant];
	return layout.cols * layout.rows;
}

export function sheetPageCount(count: number, variant: SheetVariant): number {
	return Math.max(1, Math.ceil(count / sheetCapacity(variant)));
}

// Read the artwork's own aspect from its viewBox. Artworks on one sheet may
// have been drawn on different canvases, so each cell fits its own ratio.
function aspectOf(svg: string): number {
	const viewBox = svg.match(/\sviewBox="([^"]+)"/)?.[1]?.split(/[\s,]+/).map(Number);
	if (viewBox && viewBox.length === 4 && viewBox.every(Number.isFinite) && viewBox[2] > 0 && viewBox[3] > 0) {
		return viewBox[2] / viewBox[3];
	}
	return 1;
}

function sizedSvg(svg: string, width: number, height: number): string {
	return svg.replace(/(<svg)([^>]*)/, (_match: string, tag: string, attrs: string) => {
		const cleaned = attrs.replace(/\s+width="[^"]*"/g, '').replace(/\s+height="[^"]*"/g, '');
		return `${tag}${cleaned} width="${width}" height="${height}"`;
	});
}

function loadSvgImage(svg: string, width: number, height: number): Promise<HTMLImageElement> {
	const blob = new Blob([sizedSvg(svg, width, height)], { type: 'image/svg+xml' });
	const url = URL.createObjectURL(blob);
	return new Promise<HTMLImageElement>((resolve, reject) => {
		const image = new Image();
		image.onload = () => resolve(image);
		image.onerror = () => reject(new Error('failed to rasterise artwork svg'));
		image.src = url;
	}).finally(() => URL.revokeObjectURL(url));
}

function ellipsise(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string {
	if (!text) return '';
	if (ctx.measureText(text).width <= maxWidth) return text;
	let low = 0;
	let high = text.length;
	while (low < high) {
		const mid = Math.ceil((low + high) / 2);
		if (ctx.measureText(text.slice(0, mid) + '…').width <= maxWidth) low = mid;
		else high = mid - 1;
	}
	return text.slice(0, low) + '…';
}

function drawBadge(ctx: CanvasRenderingContext2D, x: number, y: number, label: string): void {
	const radius = 17;
	ctx.beginPath();
	ctx.arc(x + radius, y + radius, radius, 0, Math.PI * 2);
	ctx.fillStyle = 'rgba(20, 20, 20, 0.82)';
	ctx.fill();
	ctx.fillStyle = '#ffffff';
	ctx.font = `600 20px ${FONT_STACK}`;
	ctx.textAlign = 'center';
	ctx.textBaseline = 'middle';
	ctx.fillText(label, x + radius, y + radius + 1);
	ctx.textAlign = 'start';
	ctx.textBaseline = 'alphabetic';
}

export async function buildContactSheet(entries: ContactSheetEntry[], options: ContactSheetOptions): Promise<Blob> {
	const layout = LAYOUTS[options.variant];
	const capacity = layout.cols * layout.rows;
	if (entries.length === 0) throw new Error('no artworks selected');
	if (entries.length > capacity) throw new Error('too many artworks for one sheet');
	const startIndex = options.startIndex ?? 0;
	// A full sheet uses the whole grid; a trailing sheet shrinks to what it holds.
	const cols = Math.min(layout.cols, entries.length);
	const rows = Math.ceil(entries.length / cols);
	const sheetW = layout.pad * 2 + cols * layout.cellW + (cols - 1) * layout.gap;
	const sheetH = layout.pad * 2 + layout.headerH + rows * (layout.cellH + layout.captionH) + (rows - 1) * layout.gap;
	// The AI sheet is emitted at the exact long edge those models resize to, so
	// the file is never resampled twice. The review sheet just stays within a
	// size the browser can allocate.
	const scale = layout.targetLongEdge
		? layout.targetLongEdge / Math.max(sheetW, sheetH)
		: Math.min(2, MAX_PIXEL_SIDE / Math.max(sheetW, sheetH));

	const canvas = document.createElement('canvas');
	canvas.width = Math.round(sheetW * scale);
	canvas.height = Math.round(sheetH * scale);
	const ctx = canvas.getContext('2d');
	if (!ctx) throw new Error('canvas 2d context unavailable');
	ctx.scale(scale, scale);
	ctx.textBaseline = 'alphabetic';

	ctx.fillStyle = '#ffffff';
	ctx.fillRect(0, 0, sheetW, sheetH);

	ctx.fillStyle = '#1a1a1a';
	ctx.font = `600 ${layout.badge ? 17 : 20}px ${FONT_STACK}`;
	ctx.fillText(options.title, layout.pad, layout.pad + 17);
	ctx.fillStyle = '#8a8a8a';
	ctx.font = `${layout.badge ? 13 : 12}px ${FONT_STACK}`;
	ctx.fillText(options.subtitle, layout.pad, layout.pad + (layout.badge ? 36 : 40));

	for (let index = 0; index < entries.length; index += 1) {
		const entry = entries[index];
		const col = index % cols;
		const row = Math.floor(index / cols);
		const cellX = layout.pad + col * (layout.cellW + layout.gap);
		const cellY = layout.pad + layout.headerH + row * (layout.cellH + layout.captionH + layout.gap);

		ctx.fillStyle = '#fbfbfa';
		ctx.fillRect(cellX, cellY, layout.cellW, layout.cellH);

		const aspect = aspectOf(entry.svg);
		const artW = Math.min(layout.cellW, layout.cellH * aspect);
		const artH = artW / aspect;
		const artX = cellX + (layout.cellW - artW) / 2;
		const artY = cellY + (layout.cellH - artH) / 2;
		try {
			const image = await loadSvgImage(entry.svg, Math.round(artW * scale), Math.round(artH * scale));
			ctx.drawImage(image, artX, artY, artW, artH);
		} catch {
			// A single unreadable artwork leaves an empty frame rather than
			// aborting the whole sheet.
		}

		ctx.strokeStyle = '#e2e0dc';
		ctx.lineWidth = 1;
		ctx.strokeRect(cellX + 0.5, cellY + 0.5, layout.cellW - 1, layout.cellH - 1);

		if (layout.badge) {
			drawBadge(ctx, cellX + 8, cellY + 8, String(startIndex + index + 1));
			continue;
		}

		ctx.font = `12px ${FONT_STACK}`;
		ctx.fillStyle = '#3a3a3a';
		ctx.fillText(ellipsise(ctx, `${startIndex + index + 1}. ${entry.caption}`, layout.cellW), cellX, cellY + layout.cellH + 17);
		ctx.font = `11px ${FONT_STACK}`;
		ctx.fillStyle = '#9a9a9a';
		ctx.fillText(ellipsise(ctx, entry.sub, layout.cellW), cellX, cellY + layout.cellH + 33);
	}

	return await new Promise<Blob>((resolve, reject) => {
		canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error('failed to encode contact sheet')), 'image/png');
	});
}
