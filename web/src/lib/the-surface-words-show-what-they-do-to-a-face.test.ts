// Run with: npm run test:unit  (node:test, no test dependency)
//
// Acceptance for the surface half of the saijiki panels. おもて was the only
// one of the eleven built-in categories with no preview of its own: all eleven
// of its words fell through to the generic fallback -- one wavy line and the
// sentence "記述の解釈に影響する語彙です。" -- so the panel said nothing about
// what any of them does.
//
// T-30 (every word of the category has its own preview, and the page reads it),
// T-31 (the copy is there in both UI languages), T-32 (eleven drawings, not one
// drawing eleven times), T-33 (they share one contour, so only the face
// changes), T-34 (空 is the empty one, and it is the only empty one),
// T-35 (the drawings carry the engine's own counts: one line set for 平行線,
// two for 交差線, three tone steps for アクアチント).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { GENERATED_SAIJIKI } from './saijiki.generated.ts';
import { SURFACE_BOX, SURFACE_PREVIEWS } from './saijiki-surface.ts';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');

/** The words the server's saijiki table puts in the category, not a copy. */
const OMOTE = GENERATED_SAIJIKI.find((cat) => cat.key === 'omote')?.words ?? [];

/** The sentence any word without an entry of its own gets instead. */
const FALLBACK = '記述の解釈に影響する語彙です。';

// ------------------------------------------------------------------- T-30

test('T-30  every word of おもて has a preview of its own', () => {
	assert.ok(OMOTE.length > 0, 'the saijiki table has no おもて category');
	for (const word of OMOTE) {
		assert.ok(SURFACE_PREVIEWS[word], `${word} has no preview and would fall back`);
	}
});

test('T-30  the previews are the category, and nothing besides', () => {
	// A preview for a word the table does not have would never be reached.
	assert.deepEqual(Object.keys(SURFACE_PREVIEWS).sort(), [...OMOTE].sort());
});

test('T-30  the page reads them, so a hover reaches the entries', () => {
	const page = read('../routes/+page.svelte');
	assert.match(page, /import \{[^}]*SURFACE_PREVIEWS[^}]*\} from '\$lib\/saijiki-surface'/);
	// Inside the table `saijikiPreview` looks words up in -- not merely imported.
	const table = page.slice(page.indexOf('const previews: Record<string, PreviewEntry>'));
	const body = table.slice(0, table.indexOf('\n\t\t};'));
	assert.match(body, /\.\.\.SURFACE_PREVIEWS,/);
});

// ------------------------------------------------------------------- T-31

test('T-31  each word says what it does, in both UI languages', () => {
	for (const word of OMOTE) {
		const entry = SURFACE_PREVIEWS[word];
		for (const field of ['effect', 'example', 'effectEn', 'exampleEn'] as const) {
			assert.ok(entry[field].trim().length > 0, `${word}: ${field} is empty`);
		}
		assert.notEqual(entry.effect, FALLBACK, `${word}: still the fallback sentence`);
		// The English half is English, so it cannot be the Japanese one copied over.
		assert.doesNotMatch(entry.effectEn, /[ぁ-んァ-ヶ一-龠]/, `${word}: effectEn has kana or kanji`);
		assert.doesNotMatch(entry.exampleEn, /[ぁ-んァ-ヶ一-龠]/, `${word}: exampleEn has kana or kanji`);
	}
});

// ------------------------------------------------------------------- T-32

test('T-32  eleven words, eleven different drawings', () => {
	const drawings = OMOTE.map((word) => SURFACE_PREVIEWS[word].svg);
	assert.equal(new Set(drawings).size, OMOTE.length, 'two surface words share a drawing');
	for (const [index, svg] of drawings.entries()) {
		assert.match(svg, /^<svg viewBox="0 0 180 92"/, `${OMOTE[index]}: not a preview-sized svg`);
		assert.match(svg, /<\/svg>$/, `${OMOTE[index]}: unclosed svg`);
	}
});

// ------------------------------------------------------------------- T-33

test('T-33  the contour is the same in all eleven; the face is what changes', () => {
	for (const word of OMOTE) {
		const svg = SURFACE_PREVIEWS[word].svg;
		assert.ok(
			svg.includes(`<rect ${SURFACE_BOX} fill="none" stroke="#2b2b2b" stroke-width="4"/>`),
			`${word}: draws its own contour instead of the shared one`
		);
		// Every interior is cut to that contour, so no word spills over the edge
		// by accident. Bleeding leaves the contour on purpose and says so.
		assert.match(svg, /clip-path="url\(#surface-clip\)"/, `${word}: interior is not clipped`);
	}
});

// ------------------------------------------------------------------- T-34

/** What a drawing puts inside the contour, with the contour itself removed. */
function interior(word: string): string {
	const svg = SURFACE_PREVIEWS[word].svg;
	const start = svg.indexOf('<g clip-path="url(#surface-clip)">');
	const end = svg.indexOf('</g>', start);
	return svg.slice(start + '<g clip-path="url(#surface-clip)">'.length, end);
}

test('T-34  空 is empty, and it is the only empty one', () => {
	assert.equal(interior('空'), '', '空 puts marks on a face it says it leaves untouched');
	for (const word of OMOTE.filter((w) => w !== '空')) {
		const svg = SURFACE_PREVIEWS[word].svg;
		const marks = interior(word) + svg.slice(svg.indexOf('</g>'), svg.lastIndexOf('<rect'));
		assert.ok(marks.includes('<'), `${word}: draws nothing, so it reads as 空`);
	}
});

// ------------------------------------------------------------------- T-35

test('T-35  a crosshatch is a hatch laid down a second time', () => {
	const hatch = SURFACE_PREVIEWS['平行線'].svg.match(/<g transform="rotate\(/g)?.length ?? 0;
	const cross = SURFACE_PREVIEWS['交差線'].svg.match(/<g transform="rotate\(/g)?.length ?? 0;
	assert.equal(hatch, 1, '平行線 should lay down one set of lines');
	assert.equal(cross, 2, '交差線 should lay down two');
	assert.ok(cross > hatch, 'the crosshatch has no more line sets than the hatch');
});

test('T-35  aquatint is drawn in three tone steps, the engine default', () => {
	// tone_steps defaults to 3 in SurfaceSpec, and the bands are the steps: the
	// dabs are cut into three x ranges, each one darker than the last.
	const opacities = [...SURFACE_PREVIEWS['アクアチント'].svg.matchAll(/opacity="([\d.]+)"/g)].map(
		(m) => Number(m[1])
	);
	assert.ok(opacities.length > 0, 'the aquatint drawing has no dabs');
	const bands = [...SURFACE_PREVIEWS['アクアチント'].svg.matchAll(/cx="([\d.]+)"/g)].map((m) =>
		Math.min(2, Math.floor((Number(m[1]) - 51) / 26))
	);
	assert.equal(new Set(bands).size, 3, 'the aquatint dabs do not fall in three bands');
	const mean = (band: number) =>
		opacities.filter((_, i) => bands[i] === band).reduce((a, b) => a + b, 0) /
		opacities.filter((_, i) => bands[i] === band).length;
	assert.ok(mean(0) < mean(1), 'the second step is not darker than the first');
	assert.ok(mean(1) < mean(2), 'the third step is not darker than the second');
});

test('T-35  the relative words move a density instead of being one', () => {
	// 濃い and 薄い are not textures. Each shows the same stipple twice -- the
	// default on the left, the value the word asks for on the right -- so the
	// dense one must carry more marks than the default and the faint one fewer.
	const dabs = (word: string) =>
		[...interior(word).matchAll(/cx="([\d.]+)"/g)].map((m) => Number(m[1]));
	for (const [word, compare] of [
		['濃い', (left: number, right: number) => right > left],
		['薄い', (left: number, right: number) => right < left]
	] as const) {
		const xs = dabs(word);
		const left = xs.filter((x) => x < 90).length;
		const right = xs.filter((x) => x >= 90).length;
		assert.ok(left > 0 && right > 0, `${word}: one half of the comparison is missing`);
		assert.ok(compare(left, right), `${word}: the two halves do not differ the way it says`);
	}
});
