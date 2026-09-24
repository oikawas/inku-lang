type HistoryGridPageSizeInput = {
	width: number;
	height: number;
	gap: number;
	minCardWidth: number;
	cardHeights: number[];
};

/** Return the number of complete thumbnail rows that fit in the grid viewport. */
export function historyGridPageSize({ width, height, gap, minCardWidth, cardHeights }: HistoryGridPageSizeInput): number {
	if (width <= 0 || height <= 0) return 1;
	const columns = Math.max(1, Math.floor((width + gap) / (minCardWidth + gap)));
	const measuredCardHeight = cardHeights.reduce(
		(maximum, value) => Number.isFinite(value) && value > 0 ? Math.max(maximum, value) : maximum,
		0,
	);
	const cardWidth = Math.max(minCardWidth, (width - gap * (columns - 1)) / columns);
	const fallbackCardHeight = Math.max(1, cardWidth - 12) * 58 / 82 + 75;
	const cardHeight = measuredCardHeight || fallbackCardHeight;
	const rows = Math.max(1, Math.floor((height + gap) / (cardHeight + gap)));
	return columns * rows;
}
