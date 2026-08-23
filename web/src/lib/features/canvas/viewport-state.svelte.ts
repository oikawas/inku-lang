export type CanvasViewport = {
	readonly zoom: number;
	readonly actualZoom: number;
	readonly canPan: boolean;
	readonly panX: number;
	readonly panY: number;
	readonly dragging: boolean;
	setZoom(nextZoom: number): void;
	fit(): void;
	updateFitZoom(nextZoom: number): void;
	startDrag(event: PointerEvent, canvasActive: boolean): void;
	moveDrag(event: PointerEvent): void;
	endDrag(event: PointerEvent): void;
};

const clampZoom = (value: number): number => Math.max(0.25, Math.min(10, +value.toFixed(2)));

/** Route-instance owner for the Canvas viewport and its direct interactions. */
export class CanvasViewportState implements CanvasViewport {
	zoom = $state(1);
	fitZoom = $state(1);
	panX = $state(0);
	panY = $state(0);
	dragging = $state(false);

	private dragStartX = 0;
	private dragStartY = 0;
	private dragStartPanX = 0;
	private dragStartPanY = 0;

	get actualZoom(): number {
		return this.fitZoom * this.zoom;
	}

	get canPan(): boolean {
		return this.zoom > 1;
	}

	setZoom(nextZoom: number): void {
		this.zoom = clampZoom(nextZoom);
		// Panning only has meaning above the fitted size. Returning to fit also
		// clears an old offset so a later zoom starts from the centered artwork.
		if (this.zoom <= 1) {
			this.panX = 0;
			this.panY = 0;
		}
	}

	fit(): void {
		// User zoom is relative to the latest measured fit. A new work resets the
		// relative transform without discarding the panel's ResizeObserver result.
		this.zoom = 1;
		this.panX = 0;
		this.panY = 0;
		this.dragging = false;
	}

	updateFitZoom(nextZoom: number): void {
		this.fitZoom = clampZoom(nextZoom);
	}

	startDrag(event: PointerEvent, canvasActive: boolean): void {
		if (!canvasActive || this.zoom <= 1 || event.button !== 0) return;
		this.dragging = true;
		this.dragStartX = event.clientX;
		this.dragStartY = event.clientY;
		this.dragStartPanX = this.panX;
		this.dragStartPanY = this.panY;
		(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
		event.preventDefault();
	}

	moveDrag(event: PointerEvent): void {
		if (!this.dragging) return;
		this.panX = this.dragStartPanX + event.clientX - this.dragStartX;
		this.panY = this.dragStartPanY + event.clientY - this.dragStartY;
	}

	endDrag(event: PointerEvent): void {
		if (!this.dragging) return;
		this.dragging = false;
		const target = event.currentTarget as HTMLElement;
		if (target.hasPointerCapture(event.pointerId)) target.releasePointerCapture(event.pointerId);
	}

	handleKeydown(event: KeyboardEvent, canvasActive: boolean): void {
		if (!canvasActive) return;
		if (event.key === '+' || event.key === '=' || event.code === 'Equal' || event.code === 'NumpadAdd') {
			this.setZoom(this.zoom + 0.25);
			event.preventDefault();
			return;
		}
		if (event.key === '-' || event.key === '_' || event.code === 'Minus' || event.code === 'NumpadSubtract') {
			this.setZoom(this.zoom - 0.25);
			event.preventDefault();
			return;
		}
		if (event.key === '0' || event.code === 'Digit0' || event.code === 'Numpad0') {
			this.fit();
			event.preventDefault();
			return;
		}
		if (!this.canPan) return;
		const step = event.shiftKey ? 120 : 40;
		if (event.key === 'ArrowLeft') this.panX += step;
		else if (event.key === 'ArrowRight') this.panX -= step;
		else if (event.key === 'ArrowUp') this.panY += step;
		else if (event.key === 'ArrowDown') this.panY -= step;
		else return;
		event.preventDefault();
	}
}
