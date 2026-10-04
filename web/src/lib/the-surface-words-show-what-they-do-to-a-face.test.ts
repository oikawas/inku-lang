// Run with: npm run test:unit  (node:test, no test dependency)
//
// Acceptance for the surface and handling saijiki panels. Each current word
// needs its own preview instead of the generic fallback's wavy line and
// "記述の解釈に影響する語彙です。". Saijiki v2 replaces 薄墨 with 刷き and
// gives 濃い / 程よい / 薄い their own handling category.
//
// T-30 (every word of the category has its own preview, and the page reads it),
// T-31 (the copy is there in both UI languages), T-32 (one drawing per word),
// T-33 (they share one contour, so only the face
// changes), T-34 (空 is the empty one, and it is the only empty one),
// T-35 (the drawings carry the engine's own counts: one line set for 平行線,
// two for 交差線, three tone steps for アクアチント).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { GENERATED_SAIJIKI } from './saijiki.generated.ts';
import { SURFACE_BOX, SURFACE_PREVIEWS, HANDLING_PREVIEWS } from './saijiki-surface.ts';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');

/** The words the server's saijiki table puts in the category, not a copy. */
const OMOTE = GENERATED_SAIJIKI.find((cat) => cat.key === 'omote')?.words ?? [];
const SABAKI = GENERATED_SAIJIKI.find((cat) => cat.key === 'sabaki')?.words ?? [];

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

test('T-30  handling has exactly its three current words and distinct previews', () => {
	assert.equal(SABAKI.length, 3);
	assert.deepEqual(Object.keys(HANDLING_PREVIEWS).sort(), [...SABAKI].sort());
	assert.equal(new Set(SABAKI.map((word) => HANDLING_PREVIEWS[word].svg)).size, SABAKI.length);
});

test('T-30  the page reads them, so a hover reaches the entries', () => {
	const page = read('../routes/+page.svelte');
	assert.match(page, /import \{[^}]*SURFACE_PREVIEWS[^}]*\} from '\$lib\/saijiki-surface'/);
	// Inside the table `saijikiPreview` looks words up in -- not merely imported.
	const table = page.slice(page.indexOf('const previews: Record<string, PreviewEntry>'));
	const body = table.slice(0, table.indexOf('\n\t\t};'));
	assert.match(body, /\.\.\.SURFACE_PREVIEWS,/);
	assert.match(body, /\.\.\.HANDLING_PREVIEWS,/);
});

// ------------------------------------------------------------------- T-31

test('T-31  each word says what it does, in both UI languages', () => {
	for (const word of [...OMOTE, ...SABAKI]) {
		const entry = SURFACE_PREVIEWS[word] ?? HANDLING_PREVIEWS[word];
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

test('T-32  every surface word has a different drawing', () => {
	const drawings = OMOTE.map((word) => SURFACE_PREVIEWS[word].svg);
	assert.equal(new Set(drawings).size, OMOTE.length, 'two surface words share a drawing');
	for (const [index, svg] of drawings.entries()) {
		assert.match(svg, /^<svg viewBox="0 0 180 92"/, `${OMOTE[index]}: not a preview-sized svg`);
		assert.match(svg, /<\/svg>$/, `${OMOTE[index]}: unclosed svg`);
	}
});

// ------------------------------------------------------------------- T-33

test('T-33  the contour is the same for every surface; the face is what changes', () => {
	for (const word of OMOTE) {
		const svg = SURFACE_PREVIEWS[word].svg;
		assert.ok(
			svg.includes(`<rect ${SURFACE_BOX} fill="none" stroke="#2b2b2b" stroke-width="4"/>`),
			`${word}: draws its own contour instead of the shared one`
		);
		// Every interior is cut to that contour, so no word spills over the edge.
		assert.match(svg, /clip-path="url\(#surface-clip\)"/, `${word}: interior is not clipped`);
	}
});

// ------------------------------------------------------------------- T-34

/** What a drawing puts inside the contour, with the contour itself removed. */
function interior(word: string, previews = SURFACE_PREVIEWS): string {
	const svg = previews[word].svg;
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

test('T-35  刷き sweeps twice at half the tool opacity without a flat underfill', () => {
	const svg = SURFACE_PREVIEWS['刷き'].svg;
	assert.equal([...svg.matchAll(/<g opacity="0\.5"/g)].length, 2);
	assert.match(svg, /rotate\(6 90 46\)/);
	assert.doesNotMatch(interior('刷き'), /<rect[^>]*fill="#2b2b2b"/);
	assert.match(SURFACE_PREVIEWS['刷き'].exampleEn, /\bsweep\b/);
});

test('T-35  handling changes opacity relative to the tool and keeps the marks', () => {
	// The left half is temperate pencil; the right has the chosen handling.
	// V2 changes opacity, so each word keeps the same number, shape and placement
	// of stipple marks. 程よい keeps the tool's opacity, rather than making it 1.
	for (const [word, factor] of [
		['濃い', 1.35],
		['程よい', 1],
		['薄い', 0.55]
	] as const) {
		const marks = [...interior(word, HANDLING_PREVIEWS).matchAll(
			/<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)" fill="#2b2b2b" opacity="([\d.]+)"/g
		)].map((m) => m.slice(1).map(Number));
		const left = marks.filter(([x]) => x < 90);
		const right = marks.filter(([x]) => x >= 90);
		assert.ok(left.length > 0 && right.length > 0, `${word}: one half is missing`);
		assert.equal(left.length, right.length, `${word}: changed the density`);
		assert.deepEqual(
			left.map(([x, y, r]) => [Number((x + 40).toFixed(1)), y, r]),
			right.map(([x, y, r]) => [x, y, r]),
			`${word}: changed the marks instead of their opacity`
		);
		const mean = (dabs: number[][]) => dabs.reduce((sum, m) => sum + m[3], 0) / dabs.length;
		assert.ok(Math.abs(mean(right) / mean(left) - factor) < 0.02, `${word}: wrong opacity factor`);
		if (word === '程よい') assert.deepEqual(left.map((m) => m[3]), right.map((m) => m[3]));
	}
});
