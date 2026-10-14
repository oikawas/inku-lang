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
	let rows = 0;
	let usedHeight = 0;
	for (let start = 0; start < cardHeights.length; start += columns) {
		const rowHeight = cardHeights.slice(start, start + columns).reduce(
			(maximum, value) => Number.isFinite(value) && value > 0 ? Math.max(maximum, value) : maximum,
			0,
		) || cardHeight;
		// A partial row may receive more works on the next fetch. Estimate their
		// height conservatively; completed rows use their own measured maximum.
		const completeRowHeight = start + columns > cardHeights.length ? Math.max(rowHeight, cardHeight) : rowHeight;
		const nextHeight = usedHeight + (rows > 0 ? gap : 0) + completeRowHeight;
		if (nextHeight > height) return columns * Math.max(1, rows);
		usedHeight = nextHeight;
		rows += 1;
	}
	// Only rows whose works have not arrived need the tallest-card estimate.
	const extraRows = Math.max(0, Math.floor((height - usedHeight + (rows === 0 ? gap : 0)) / (cardHeight + gap)));
	return columns * Math.max(1, rows + extraRows);
}
