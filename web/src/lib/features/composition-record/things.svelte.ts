// The displayed work's things, joined to its drawing, instructions and caption
// (2026-11-13, step 1c). One owner for the page: the "composition and laws"
// section, the DDL view, the canvas and the caption read it, and each reports
// the thing pointed at. The units are fetched only while the section is open,
// once per work and DDL; an answer for a work no longer shown is dropped
// (SPEC 7.8: a late answer never lands on another work).

import type { ApiFetch } from '$lib/transport/api-fetch';
import { LatestRequest, readUnits, thingAt, thingBox, thingLines, thingOfLine, type Box, type ThingUnit } from './things';

export class ThingLinks {
	units = $state.raw<ThingUnit[]>([]);
	/** The thing a row, the drawing or the DDL is pointing at. */
	active = $state<number | null>(null);
	private key: string | null = null;
	private readonly requests = new LatestRequest();

	/** Loads the units for a saved work's DDL, unless they are already loaded or loading. */
	load(fetch: ApiFetch, workId: string, ddl: string): void {
		const key = `${workId}\n${ddl}`;
		if (key === this.key) return;
		this.key = key;
		this.units = [];
		this.active = null;
		const token = this.requests.begin();
		void fetch(`/api/history/${encodeURIComponent(workId)}/composition-boxes`)
			.then(async (response) => (response.ok ? readUnits(await response.json()) : []))
			.catch(() => [])
			.then((units) => { if (this.requests.current(token)) this.units = units; });
	}

	/** Nothing to join: no saved work, or the section is folded. */
	clear(): void {
		this.requests.reset();
		this.key = null;
		this.units = [];
		this.active = null;
	}

	point(thing: number | null): void { if (this.active !== thing) this.active = thing; }
	pointAt(x: number, y: number): void { this.point(thingAt(this.units, x, y)); }
	pointLine(line: number | null): void { this.point(line === null ? null : thingOfLine(this.units, line)); }

	get activeLines(): number[] { return thingLines(this.units, this.active); }
	get activeBox(): Box | null { return thingBox(this.units, this.active); }
	/** Whether any chunk has a box, so the drawing can be pointed at. */
	get hasBoxes(): boolean { return this.units.some((unit) => unit.thing !== null && unit.box !== null); }
}
