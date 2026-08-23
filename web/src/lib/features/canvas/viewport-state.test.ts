import assert from 'node:assert/strict';
import { test } from 'node:test';

const identity = <T>(value: T): T => value;
const runeHost = globalThis as unknown as Record<string, unknown>;
runeHost.$state = identity;

const { CanvasViewportState } = await import('./viewport-state.svelte.ts');

function keyboardEvent(key: string, code = '', shiftKey = false): KeyboardEvent & { prevented: boolean } {
	return {
		key,
		code,
		shiftKey,
		prevented: false,
		preventDefault() { this.prevented = true; }
	} as unknown as KeyboardEvent & { prevented: boolean };
}

test('T-300/T-302: zoom, fit, and keyboard pan preserve the Canvas rules', () => {
	const viewport = new CanvasViewportState();
	viewport.setZoom(2.347);
	assert.equal(viewport.zoom, 2.35);

	const left = keyboardEvent('ArrowLeft');
	viewport.handleKeydown(left, true);
	assert.equal(viewport.panX, 40);
	assert.equal(left.prevented, true);

	const shiftedUp = keyboardEvent('ArrowUp', '', true);
	viewport.handleKeydown(shiftedUp, true);
	assert.equal(viewport.panY, 120);

	const inactive = keyboardEvent('ArrowRight');
	viewport.handleKeydown(inactive, false);
	assert.equal(viewport.panX, 40);
	assert.equal(inactive.prevented, false);

	viewport.setZoom(1);
	assert.deepEqual([viewport.zoom, viewport.panX, viewport.panY], [1, 0, 0]);
	viewport.updateFitZoom(0.1);
	assert.equal(viewport.actualZoom, 0.25);
	viewport.updateFitZoom(12);
	assert.equal(viewport.actualZoom, 10);

	viewport.setZoom(3);
	viewport.panX = 7;
	viewport.panY = -8;
	viewport.fit();
	assert.deepEqual(
		[viewport.zoom, viewport.panX, viewport.panY, viewport.dragging],
		[1, 0, 0, false]
	);
});

test('T-301: primary pointer drag keeps capture, delta, and release semantics', () => {
	const viewport = new CanvasViewportState();
	viewport.setZoom(2);
	const captured: number[] = [];
	const released: number[] = [];
	const target = {
		setPointerCapture(id: number) { captured.push(id); },
		hasPointerCapture(id: number) { return captured.includes(id) && !released.includes(id); },
		releasePointerCapture(id: number) { released.push(id); }
	};
	let prevented = false;
	const start = {
		button: 0,
		clientX: 10,
		clientY: 20,
		pointerId: 4,
		currentTarget: target,
		preventDefault() { prevented = true; }
	} as unknown as PointerEvent;

	viewport.startDrag(start, true);
	assert.equal(viewport.dragging, true);
	assert.deepEqual(captured, [4]);
	assert.equal(prevented, true);

	viewport.moveDrag({ clientX: 35, clientY: 5 } as PointerEvent);
	assert.deepEqual([viewport.panX, viewport.panY], [25, -15]);
	viewport.endDrag({ pointerId: 4, currentTarget: target } as unknown as PointerEvent);
	assert.equal(viewport.dragging, false);
	assert.deepEqual(released, [4]);

	const ignored = { ...start, button: 1 } as PointerEvent;
	viewport.startDrag(ignored, true);
	assert.equal(viewport.dragging, false);
	viewport.startDrag(start, false);
	assert.equal(viewport.dragging, false);
});

test('T-302: zoom keyboard shortcuts retain key and code aliases', () => {
	const viewport = new CanvasViewportState();
	const add = keyboardEvent('x', 'NumpadAdd');
	viewport.handleKeydown(add, true);
	assert.equal(viewport.zoom, 1.25);
	assert.equal(add.prevented, true);

	const subtract = keyboardEvent('_', 'Minus');
	viewport.handleKeydown(subtract, true);
	assert.equal(viewport.zoom, 1);

	viewport.setZoom(4);
	viewport.panX = 12;
	const reset = keyboardEvent('x', 'Numpad0');
	viewport.handleKeydown(reset, true);
	assert.deepEqual([viewport.zoom, viewport.panX], [1, 0]);
});
