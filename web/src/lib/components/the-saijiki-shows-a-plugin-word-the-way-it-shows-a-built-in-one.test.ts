// Run with: npm run test:unit  (node:test, no test dependency)
//
// Acceptance for the plugin half of the saijiki panels. T-20 (the chips are
// built-in chips with one accent, packed the same way), T-21 (the explanation
// is in the preview above, not under each chip), T-22 (the preview is the same
// four parts a built-in word gets), T-23 (the artwork is a raster shown at the
// size it was baked at).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');

// Both panels render the same list. Svelte scopes styles per component, so a
// rule written in one is not shared with the other -- every claim below has to
// hold in both files or it holds in neither panel.
const PANELS = ['./SaijikiDrawer.svelte', './SaijikiInline.svelte'];

/** The plugin section of a panel: from its heading to the end of that block. */
function pluginSection(source: string): string {
	const start = source.indexOf('{#if pluginEntries.length > 0}');
	assert.ok(start > 0, 'the panel has no plugin section');
	const end = source.indexOf('</style>', start);
	return source.slice(start, end);
}

// --------------------------------------------------------- T-20 (the chips)

test('T-20: a plugin chip is a saijiki chip, so it is the built-in size', () => {
	for (const panel of PANELS) {
		const source = read(panel);
		const section = pluginSection(source);
		// The size comes from `.saijiki-chip`; `plugin-chip` may only add accent.
		assert.match(section, /class="saijiki-chip plugin-chip"/, panel);
		const accent = source.match(/\.saijiki-chip\.plugin-chip \{([^}]*)\}/);
		assert.ok(accent, `${panel}: no plugin chip rule`);
		for (const property of ['padding', 'font-size', 'line-height', 'border-radius']) {
			assert.doesNotMatch(
				accent[1],
				new RegExp(`\\b${property}\\s*:`),
				`${panel}: plugin chips set their own ${property}`
			);
		}
	}
});

test('T-20: the accent is blue, and it comes from the tokens', () => {
	for (const panel of PANELS) {
		const source = read(panel);
		// The old accent was a pair of hard-coded reds plus a dark-theme copy.
		assert.doesNotMatch(source, /#9f4b3b|#f0a58f|185,\s*88,\s*69|226,\s*138,\s*112/, panel);
		const accent = source.match(/\.saijiki-chip\.plugin-chip \{([^}]*)\}/);
		assert.ok(accent);
		assert.match(accent[1], /var\(--accent\)/, panel);
		assert.match(accent[1], /var\(--accent-light\)/, panel);
		assert.match(source, /\.saijiki-cat\.plugin-cat \{[^}]*var\(--accent\)/, panel);
		// A hard-coded colour needs a second rule for dark; a token does not.
		assert.doesNotMatch(source, /data-theme='dark'\]\) \.saijiki-chip\.plugin-chip/, panel);
	}
});

test('T-20: plugin words are packed, not stacked one per row', () => {
	for (const panel of PANELS) {
		const source = read(panel);
		const section = pluginSection(source);
		// The column wrapper is what made each word take a row of its own.
		assert.doesNotMatch(section, /plugin-word-with-note/, panel);
		assert.doesNotMatch(source, /\.plugin-word-with-note/, panel);
		// They sit in the same wrapping row the built-in words use.
		assert.match(section, /<div class="saijiki-chips">/, panel);
	}
});

// --------------------------------------------------- T-21 (where the note is)

test('T-21: the note is not printed under the chip any more', () => {
	for (const panel of PANELS) {
		const source = read(panel);
		const section = pluginSection(source);
		assert.doesNotMatch(section, /plugin-note/, panel);
		assert.doesNotMatch(source, /\.plugin-note/, panel);
		// Nor as a title attribute, which was the drawer's version of the same.
		assert.doesNotMatch(section, /title=\{/, panel);
	}
});

test('T-21: a plugin chip reaches the preview the same ways a built-in one does', () => {
	for (const panel of PANELS) {
		const section = pluginSection(read(panel));
		assert.match(section, /onpointerenter=\{\(\) => \(activePreview = previewForPlugin\(entry\)\)\}/, panel);
		assert.match(section, /onfocus=\{\(\) => \(activePreview = previewForPlugin\(entry\)\)\}/, panel);
	}
});

test('T-21: clicking keeps each panel\'s own job', () => {
	// The drawer is read-only, so a click previews; the editor inserts the word.
	const drawer = pluginSection(read('./SaijikiDrawer.svelte'));
	assert.match(drawer, /onclick=\{\(\) => \(activePreview = previewForPlugin\(entry\)\)\}/);
	const inline = pluginSection(read('./SaijikiInline.svelte'));
	assert.match(inline, /onclick=\{\(\) => onInsertWord\(entry\.qualified_name\)\}/);
});

// ------------------------------------------------------ T-22 (the four parts)

test('T-22: a plugin preview is built from the document, not invented', () => {
	const page = read('../../routes/+page.svelte');
	const fn = page.slice(
		page.indexOf('function pluginPreview('),
		page.indexOf('// ── Color catalog')
	);
	assert.ok(fn.length > 0, 'the page builds no plugin preview');
	// Title, effect, example: the qualified name, the note, the first phrase a
	// description would use to reach the word.
	assert.match(fn, /word: entry\.qualified_name/);
	assert.match(fn, /effect: \(isJa \? entry\.note_ja : entry\.note_en\)/);
	assert.match(fn, /example: firesOn\[0\]/);
	// Both languages are read, so an English UI does not show Japanese prose.
	assert.match(fn, /isJa \? entry\.fires_on_ja : entry\.fires_on_en/);
});

test('T-22: both panels are given the builder, or one of them shows nothing', () => {
	const page = read('../../routes/+page.svelte');
	const wired = page.match(/previewForPlugin=\{pluginPreview\}/g) ?? [];
	// The drawer takes it directly; the editor dialog passes it to the inline
	// panel. Two call sites, and a missing one is a silent dead panel.
	assert.equal(wired.length, 2);
	const dialog = read('./DdlEditorDialog.svelte');
	assert.match(dialog, /previewForPlugin: \(entry: PluginEntry\) => SaijikiPreview;/);
	assert.match(dialog, /\{previewForPlugin\}/);
});

// --------------------------------------------------------- T-23 (the artwork)

test('T-23: the artwork is a raster in an img, never markup', () => {
	for (const panel of PANELS) {
		const source = read(panel);
		const art = source.slice(source.indexOf('<div class="saijiki-preview-art">'));
		assert.match(art, /<img\s/, panel);
		assert.match(art, /src=\{activePreview\.image\}/, panel);
		// The HiDPI file is offered as 2x rather than swapped in blindly.
		assert.match(art, /activePreview\.image2x \? `\$\{activePreview\.image\} 1x, \$\{activePreview\.image2x\} 2x`/, panel);
		// A word with no artwork still shows the built-in fallback drawing.
		assert.match(art, /\{:else\}[\s\S]*?\{@html activePreview\.svg\}/, panel);
	}
});

test('T-23: the frame is the size the picture is baked at, in both panels', () => {
	// 216x92 is the bake size. A frame of another size would scale the raster,
	// and a judgement made on a scaled drawing is the accident this avoids.
	for (const panel of PANELS) {
		const source = read(panel);
		const rule = source.match(/\.saijiki-preview-art \{([^}]*)\}/);
		assert.ok(rule, `${panel}: no art frame rule`);
		assert.match(rule[1], /width:\s*216px/, panel);
		assert.match(rule[1], /height:\s*92px/, panel);
	}
});

test('T-23: the page names no artwork of its own for plugin words', () => {
	const page = read('../../routes/+page.svelte');
	const fn = page.slice(
		page.indexOf('function pluginPreview('),
		page.indexOf('// ── Color catalog')
	);
	// The picture comes from the server as a URL; the only thing the page
	// supplies is the fallback for a word that ships none.
	assert.match(fn, /image: entry\.preview_url \|\| undefined/);
	assert.match(fn, /image2x: entry\.preview_url_2x \|\| undefined/);
	assert.match(fn, /svg: PLUGIN_FALLBACK_SVG/);
});
