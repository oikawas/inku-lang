// Contact sheet: lay selected artworks out on one sheet and rasterise it to PNG.
// Each artwork is drawn separately into the canvas, so ids that repeat across
// SVG documents (texture filters, clip paths) can never collide.

export type ContactSheetEntry = {
	svg: string;
	caption: string;
	sub: string;
};

export type ContactSheetOptions = {
	title: string;
	subtitle: string;
};

const CELL_W = 300;
const CELL_H = 220;
const CAPTION_H = 44;
const GAP = 18;
const PAD = 32;
const HEADER_H = 58;
const MAX_PIXEL_SIDE = 6000;
const FONT_STACK = 'system-ui, -apple-system, "Hiragino Sans", "Noto Sans JP", sans-serif';

function columnsFor(count: number): number {
	if (count <= 1) return 1;
	return Math.max(2, Math.min(8, Math.ceil(Math.sqrt(count))));
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

export async function buildContactSheet(entries: ContactSheetEntry[], options: ContactSheetOptions): Promise<Blob> {
	if (entries.length === 0) throw new Error('no artworks selected');
	const cols = columnsFor(entries.length);
	const rows = Math.ceil(entries.length / cols);
	const sheetW = PAD * 2 + cols * CELL_W + (cols - 1) * GAP;
	const sheetH = PAD * 2 + HEADER_H + rows * (CELL_H + CAPTION_H) + (rows - 1) * GAP;
	// Keep the sheet within a size the browser can actually allocate.
	const scale = Math.min(2, MAX_PIXEL_SIDE / Math.max(sheetW, sheetH));

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
	ctx.font = `600 20px ${FONT_STACK}`;
	ctx.fillText(options.title, PAD, PAD + 20);
	ctx.fillStyle = '#8a8a8a';
	ctx.font = `12px ${FONT_STACK}`;
	ctx.fillText(options.subtitle, PAD, PAD + 40);

	for (let index = 0; index < entries.length; index += 1) {
		const entry = entries[index];
		const col = index % cols;
		const row = Math.floor(index / cols);
		const cellX = PAD + col * (CELL_W + GAP);
		const cellY = PAD + HEADER_H + row * (CELL_H + CAPTION_H + GAP);

		ctx.fillStyle = '#fbfbfa';
		ctx.fillRect(cellX, cellY, CELL_W, CELL_H);

		const aspect = aspectOf(entry.svg);
		const artW = Math.min(CELL_W, CELL_H * aspect);
		const artH = artW / aspect;
		const artX = cellX + (CELL_W - artW) / 2;
		const artY = cellY + (CELL_H - artH) / 2;
		try {
			const image = await loadSvgImage(entry.svg, Math.round(artW * scale), Math.round(artH * scale));
			ctx.drawImage(image, artX, artY, artW, artH);
		} catch {
			// A single unreadable artwork leaves an empty frame rather than
			// aborting the whole sheet.
		}

		ctx.strokeStyle = '#e2e0dc';
		ctx.lineWidth = 1;
		ctx.strokeRect(cellX + 0.5, cellY + 0.5, CELL_W - 1, CELL_H - 1);

		ctx.font = `12px ${FONT_STACK}`;
		ctx.fillStyle = '#3a3a3a';
		ctx.fillText(ellipsise(ctx, `${index + 1}. ${entry.caption}`, CELL_W), cellX, cellY + CELL_H + 17);
		ctx.font = `11px ${FONT_STACK}`;
		ctx.fillStyle = '#9a9a9a';
		ctx.fillText(ellipsise(ctx, entry.sub, CELL_W), cellX, cellY + CELL_H + 33);
	}

	return await new Promise<Blob>((resolve, reject) => {
		canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error('failed to encode contact sheet')), 'image/png');
	});
}
