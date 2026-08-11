/**
 * Where a listed work's picture comes from.
 *
 * The listing draws a PNG baked from the work's stored SVG rather than the SVG
 * itself: one page of history was 23.5 MB of pictures, and the same page of
 * thumbnails is about 0.5 MB. A work that has no thumbnail yet has no entry
 * here and the caller falls back to the SVG.
 */

export type ThumbnailItem = {
	id?: string;
	render_hash?: string | null;
};

export type ThumbnailConditions = {
	/** Whether this server keeps the second size. Off by default. */
	hidpi: boolean;
	/** window.devicePixelRatio. Asking for the larger size is only worth it above 1. */
	devicePixelRatio: number;
};

/** The second size exists only where both the server keeps it and the screen uses it. */
export function thumbnailScale(conditions: ThumbnailConditions): 1 | 2 {
	return conditions.hidpi && conditions.devicePixelRatio > 1 ? 2 : 1;
}

/**
 * The URL of one work's thumbnail, or null when there can be no thumbnail.
 *
 * `v` carries the work's render hash. The response is cached for a year and
 * marked immutable, which is true of a saved work's picture but not of the
 * file: an administrator can rebuild it. Naming the source in the URL means a
 * rebuilt thumbnail arrives under an address the cache has not seen, instead of
 * being invisible until the cache expires.
 */
export function thumbnailSrc(item: ThumbnailItem, conditions: ThumbnailConditions): string | null {
	if (!item.id) return null;
	const params = new URLSearchParams({ scale: String(thumbnailScale(conditions)) });
	if (item.render_hash) params.set('v', item.render_hash);
	return `/api/history/${encodeURIComponent(item.id)}/thumb?${params.toString()}`;
}

// The server's answer, learned once from /api/info. A module-level value rather
// than a prop: every thumbnail on screen wants the same one, and threading it
// through six call sites would be six chances to forget.
let hidpi = false;

export function setThumbnailHidpi(enabled: boolean): void {
	hidpi = enabled;
}

export function thumbnailConditions(): ThumbnailConditions {
	return {
		hidpi,
		devicePixelRatio: typeof window === 'undefined' ? 1 : window.devicePixelRatio || 1
	};
}
