// Run with: npm run test:unit  (node:test, no test dependency)
//
// T-315: Contact-sheet notes record the catalog used for this work. A catalog
// tagline is catalog metadata, not a fact about the work, so it must not be
// appended to the saved catalog name or reintroduced through this reader.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { noteEntryFor, type ContactSheetNoteDeps } from "./note-entry.ts";

const NOTE_ENTRY = fileURLToPath(new URL("./note-entry.ts", import.meta.url));

const deps: ContactSheetNoteDeps = {
	catalogName: (id) => `catalog fallback for ${id ?? "none"}`,
	formatDate: () => "2026-08-20",
};

test("T-315 contact-sheet notes keep the catalog name, never its tagline", () => {
	assert.equal(
		noteEntryFor(
			{
				at: 0,
				render_color_catalog_name: "Hokusai",
				// This is deliberately an excess saved/API field: the contact-sheet
				// reader must neither type nor read it.
				render_color_catalog_sub: "A wave of blue",
			} as Parameters<typeof noteEntryFor>[0],
			deps,
		).colorCatalog,
		"Hokusai",
	);
	assert.equal(
		noteEntryFor({ at: 0, render_color_catalog_name: "Hokusai" }, deps).colorCatalog,
		"Hokusai",
	);
	assert.equal(
		noteEntryFor({ at: 0, render_color_catalog_id: "hokusai" }, deps).colorCatalog,
		"catalog fallback for hokusai",
	);
	assert.doesNotMatch(readFileSync(NOTE_ENTRY, "utf8"), /render_color_catalog_sub/);
});
