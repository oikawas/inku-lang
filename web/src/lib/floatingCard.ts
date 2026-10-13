// A card fixed to the window and placed beside the element it describes. A card
// laid out inside its anchor is cut off by any scrolling list or dialog edge
// around it: the model selection dialog cut the model card at its bottom once the
// card had grown a row (the author asked for a fix, 2026-10-13). Fixed to the
// window, nothing around it clips it. It opens below the anchor when it fits,
// above when there is more room there, and stays inside the window either way.

export type AnchorBox = { top: number; bottom: number; left: number };

export function floatingCardPosition(
	anchor: AnchorBox,
	card: { width: number; height: number },
	viewport: { width: number; height: number },
	gap = 6,
	margin = 8
): { top: number; left: number } {
	const below = viewport.height - anchor.bottom - gap - margin;
	const above = anchor.top - gap - margin;
	const top = card.height <= below || below >= above ? anchor.bottom + gap : anchor.top - gap - card.height;
	return {
		top: Math.max(margin, Math.min(top, viewport.height - card.height - margin)),
		left: Math.max(margin, Math.min(anchor.left, viewport.width - card.width - margin))
	};
}

// The parent's :hover or :focus rule still decides when the card shows. It is
// measured on the next frame, once that rule has laid it out, and kept hidden
// until it stands in its place, so it never flashes where it last was.
export function openFloatingCard(card: HTMLElement, anchor: HTMLElement): void {
	card.style.visibility = 'hidden';
	requestAnimationFrame(() => {
		const { top, left } = floatingCardPosition(
			anchor.getBoundingClientRect(),
			{ width: card.offsetWidth, height: card.offsetHeight },
			{ width: window.innerWidth, height: window.innerHeight }
		);
		card.style.top = `${top}px`;
		card.style.left = `${left}px`;
		card.style.visibility = '';
	});
}
