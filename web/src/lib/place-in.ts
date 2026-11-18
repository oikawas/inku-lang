/** Move a component's existing controls to a stable host without remounting them. */
export function placeIn(node: HTMLElement, target: HTMLElement | null) {
	const marker = document.createComment('place-in');
	node.before(marker);
	function place(next: HTMLElement | null) {
		if (next) next.appendChild(node);
		else if (marker.parentNode) marker.after(node);
	}
	place(target);
	return { update: place, destroy() { node.remove(); marker.remove(); } };
}
