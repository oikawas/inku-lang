// "Change the layout" on a work written in words (step 3, 2026-11-13; the mock's
// section 7): choose a thing and press a place, and the work is drawn again with
// only that thing's numbers moved there (the shared core's chunk `place`, no send).
// These are the pure parts: the places and their pads, each thing's row and the
// option's label.

import type { ThingUnit } from '../composition-record/things.ts';
import { placeName, roleName } from '../composition-record/composition-names.ts';

/** What the dialog offers: the work, its chunks and its record's things. */
export type PlaceTarget = {
	workId: string | null;
	units: ThingUnit[];
	things: { thing: number; role: string; what: string }[];
};

/** The nine places, as the core names them (chunk_moves.rs `PLACES`), with where each sits. */
export const PLACES = [
	{ id: 'golden_ul', pad: 'golden', x: 0.382, y: 0.382 },
	{ id: 'golden_ur', pad: 'golden', x: 0.618, y: 0.382 },
	{ id: 'golden_ll', pad: 'golden', x: 0.382, y: 0.618 },
	{ id: 'golden_lr', pad: 'golden', x: 0.618, y: 0.618 },
	{ id: 'third_left', pad: 'third', x: 1 / 3, y: null },
	{ id: 'third_right', pad: 'third', x: 2 / 3, y: null },
	{ id: 'third_top', pad: 'third', x: null, y: 1 / 3 },
	{ id: 'third_bottom', pad: 'third', x: null, y: 2 / 3 },
	{ id: 'center', pad: 'center', x: 0.5, y: 0.5 },
] as const;
export type PlaceId = typeof PLACES[number]['id'];

/** How near a center is to a place for the place to be its own (the core's 0.02). */
const NEAR = 0.02;

/** The place a box's center is at: a point before a line, as the core reads it. */
export function placeOfBox(box: readonly [number, number, number, number] | null): PlaceId | null {
	if (!box) return null;
	const [cx, cy] = [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2];
	const near = (place: number | null, value: number) => place === null || Math.abs(place - value) <= NEAR;
	let line: PlaceId | null = null;
	for (const place of PLACES) {
		if (!near(place.x, cx) || !near(place.y, cy)) continue;
		if (place.x !== null && place.y !== null) return place.id;
		line ??= place.id;
	}
	return line;
}

/** Whether a place's outcome lets the thing move there. */
export function movable(outcome: string | undefined): boolean {
	return outcome === 'ok' || outcome === 'clamped';
}

export type PlaceRow = {
	title: string;
	number: number;
	role: string;
	what: string;
	now: PlaceId | null;
	places: Readonly<Record<string, string>>;
	box: readonly [number, number, number, number] | null;
	movable: boolean;
};

/** One row per chunk: its thing's number, role and what it is (its title when the record
 *  names none), where it is now, and whether any place takes it. */
export function placeRows(target: PlaceTarget, isJapanese: boolean): PlaceRow[] {
	return target.units.flatMap((unit, index) => {
		if (!unit.title) return [];
		const thing = unit.thing === null ? undefined : target.things.find((entry) => entry.thing === unit.thing);
		return [{
			title: unit.title,
			number: unit.thing ?? index + 1,
			role: thing?.role ? roleName(thing.role, isJapanese) : '',
			what: thing?.what || unit.title,
			now: placeOfBox(unit.box),
			places: unit.places,
			box: unit.box,
			movable: Object.values(unit.places).some(movable),
		}];
	});
}

/** Whether the dialog offers the places: some chunk can move somewhere. */
export function offersPlaces(target: PlaceTarget): boolean {
	return target.units.some((unit) => Object.values(unit.places).some(movable));
}

/** An option's label: "磯の岩肌 → 黄金分割・左上の交点", with the edge note when it stops short. */
export function placeLabel(row: PlaceRow, at: PlaceId, isJapanese: boolean, clampedNote: string): string {
	const label = `${row.what} → ${placeName(at, isJapanese)}`;
	return row.places[at] === 'clamped' ? `${label}${clampedNote}` : label;
}
