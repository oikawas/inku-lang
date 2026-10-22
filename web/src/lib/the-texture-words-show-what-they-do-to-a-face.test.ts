// Run with: npm run test:unit  (node:test, no test dependency)
//
// Acceptance for the fineness (きめ) and underlayer (したじ) saijiki panels
// (DDL 24). Each word needs its own preview instead of the generic fallback's
// wavy line and "記述の解釈に影響する語彙です。".
//
// T-36 (every word of the two categories has its own preview, and the page
// reads it), T-37 (the copy is there in both UI languages), T-38 (one drawing
// per word, on the shared contour), T-39 (the drawings carry render engine
// 89's factors: a dot's size and how many lie, and the paint under them).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { GENERATED_SAIJIKI } from './saijiki.generated.ts';
import { SURFACE_BOX, FINENESS_PREVIEWS, UNDERLAYER_PREVIEWS } from './saijiki-surface.ts';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');

/** The words the server's saijiki table puts in each category, not a copy. */
const KIME = GENERATED_SAIJIKI.find((cat) => cat.key === 'kime')?.words ?? [];
const SHITAJI = GENERATED_SAIJIKI.find((cat) => cat.key === 'shitaji')?.words ?? [];

/** The sentence any word without an entry of its own gets instead. */
const FALLBACK = '記述の解釈に影響する語彙です。';

const entry = (word: string) => FINENESS_PREVIEWS[word] ?? UNDERLAYER_PREVIEWS[word];

// ------------------------------------------------------------------- T-36

test('T-36  every word of きめ and したじ has a preview, and nothing besides', () => {
	assert.deepEqual(KIME, ['細かい', '粗い', '密な', '疎な']);
	assert.deepEqual(SHITAJI, ['下塗り']);
	assert.deepEqual(Object.keys(FINENESS_PREVIEWS).sort(), [...KIME].sort());
	assert.deepEqual(Object.keys(UNDERLAYER_PREVIEWS).sort(), [...SHITAJI].sort());
});

test('T-36  the page reads them, so a hover reaches the entries', () => {
	const page = read('../routes/+page.svelte');
	const table = page.slice(page.indexOf('const previews: Record<string, PreviewEntry>'));
	const body = table.slice(0, table.indexOf('\n\t\t};'));
	assert.match(body, /\.\.\.FINENESS_PREVIEWS,/);
	assert.match(body, /\.\.\.UNDERLAYER_PREVIEWS,/);
});

// ------------------------------------------------------------------- T-37

test('T-37  each word says what it does, in both UI languages', () => {
	for (const word of [...KIME, ...SHITAJI]) {
		for (const field of ['effect', 'example', 'effectEn', 'exampleEn'] as const) {
			assert.ok(entry(word)[field].trim().length > 0, `${word}: ${field} is empty`);
		}
		assert.notEqual(entry(word).effect, FALLBACK, `${word}: still the fallback sentence`);
		assert.doesNotMatch(entry(word).effectEn, /[ぁ-んァ-ヶ一-龠]/, `${word}: effectEn has kana or kanji`);
		assert.doesNotMatch(entry(word).exampleEn, /[ぁ-んァ-ヶ一-龠]/, `${word}: exampleEn has kana or kanji`);
		// The example is DDL that writes the word itself.
		assert.ok(entry(word).example.includes(word), `${word}: the example does not write it`);
	}
});

// ------------------------------------------------------------------- T-38

test('T-38  one drawing per word, on the contour every surface shares', () => {
	const words = [...KIME, ...SHITAJI];
	assert.equal(new Set(words.map((word) => entry(word).svg)).size, words.length);
	for (const word of words) {
		const svg = entry(word).svg;
		assert.ok(
			svg.includes(`<rect ${SURFACE_BOX} fill="none" stroke="#2b2b2b" stroke-width="4"/>`),
			`${word}: draws its own contour instead of the shared one`
		);
		assert.match(svg, /clip-path="url\(#surface-clip\)"/, `${word}: interior is not clipped`);
	}
});

// ------------------------------------------------------------------- T-39

type Dot = { x: number; r: number; fill: string; opacity: number };

/** The dots of a drawing, the default half (left) and the word's half (right). */
function halves(word: string): [Dot[], Dot[]] {
	const dots = [
		...entry(word).svg.matchAll(
			/<circle cx="([\d.]+)" cy="[\d.]+" r="([\d.]+)" fill="(#[0-9a-f]{6})" opacity="([\d.]+)"/g
		)
	].map((m) => ({ x: Number(m[1]), r: Number(m[2]), fill: m[3], opacity: Number(m[4]) }));
	return [dots.filter((dot) => dot.x < 90), dots.filter((dot) => dot.x >= 90)];
}

test('T-39  fineness sizes and counts the dots as render engine 89 does', () => {
	// The halves draw their dots from the same hash, so the n-th dot of each
	// has the same jitter, and their radii stand in the word's size factor.
	for (const [word, size, count] of [
		['細かい', 0.5, 4],
		['粗い', 2, 0.25],
		['密な', 1, 4],
		['疎な', 1, 0.25]
	] as const) {
		const [left, right] = halves(word);
		assert.equal(left.length, 21, `${word}: the default half changed`);
		assert.equal(right.length, Math.floor(21 * count), `${word}: wrong number of dots`);
		for (let i = 0; i < Math.min(left.length, right.length); i += 1) {
			assert.ok(Math.abs(right[i].r / left[i].r - size) < 0.02 * size, `${word}: dot ${i} is not ×${size}`);
		}
		if (size !== 1) {
			// 細かい and 粗い keep the cover: the count goes by the inverse square.
			assert.equal(count * size * size, 1, `${word}: the cover changes`);
		}
	}
});

test('T-39  下塗り paints the tool colour under lighter dots, twice as strong up to 0.75', () => {
	const svg = entry('下塗り').svg;
	assert.match(svg, /<rect x="91" y="20" width="39" height="52" fill="#2b2b2b"\/>/);
	const [left, right] = halves('下塗り');
	assert.equal(left.length, right.length, 'the underlayer changed the dots');
	assert.ok(left.every((dot) => dot.fill === '#2b2b2b'), 'the default half is not the tool colour');
	// 45% toward white from #2b2b2b.
	assert.ok(right.every((dot) => dot.fill === '#8a8a8a'), 'the dots over the paint are not lighter');
	for (let i = 0; i < left.length; i += 1) {
		assert.ok(Math.abs(right[i].opacity / left[i].opacity - 0.75 / 0.66) < 0.05, `dot ${i}: not twice as strong, capped`);
	}
});
