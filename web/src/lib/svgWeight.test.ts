// Run with: npm run test:unit  (node:test, no test dependency)
//
// Acceptance for the three weights of a drawing. The generation info drawer
// already said how many bytes the SVG is, but bytes alone do not say why a
// drawing is heavy: at render engine 33 the two largest cases in the reference
// corpus were 224,749 B / 158 objects and 222,230 B / 680 objects. The same
// 220 KB, made of four times the number of shapes.
//
// The danger this file guards is not that a number is wrong, but that the two
// places that count are counting different things. `measureSvgWeight` here and
// `measure()` in no-git-sync/scripts/svg_weight.py are one pair: the first
// says what one work weighs, the second says how that weight has moved across
// engine versions. If they drift, neither number can be used again.
//
// T-67 (the five structural tags are not objects), T-68 (points come from both
// `points` and `d`), T-69 (a work with no SVG shows three dashes, not three
// zeros), T-70 (the two new hint keys stand in all three i18n faces),
// T-71 (one known drawing, three numbers, all agreeing with svg_weight.py).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { measureSvgWeight } from './svgWeight.ts';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const PANEL = read('./components/CanvasPanel.svelte');

// The known drawing of T-71. It is small enough to read, and it holds one of
// every branch the count has: all five excluded tags, a `<defs>` with a drawn
// child inside it, an `id` that must not be read as a `d`, points written with
// commas and with runs of spaces, an empty `points`, a `d` with an even count
// of numbers and a `d` with an odd one.
const FIXTURE = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">
<title>weight fixture</title>
<desc>a drawing that exercises every branch of the count</desc>
<metadata>id="this is not a path"</metadata>
<defs>
<pattern id="ground" width="4" height="4" patternUnits="userSpaceOnUse">
<rect width="4" height="4" fill="#eeeeee" />
</pattern>
</defs>
<g id="marks">
<rect x="1" y="2" width="10" height="20" fill="url(#ground)" />
<circle cx="5.5" cy="6.5" r="1e1" />
<path id="not-a-d-attribute" d="M 0 0 L 10 10 L 20 0 Z" />
<path d="M1.5,2.5 C 3 4 5 6 7.5 8.5 L 9 10 11" />
<polyline points="0,0 1,1  2,2   3,3" />
<polygon points=" 4,4 5,5 " />
<polyline points="" />
</g>
</svg>`;

// ------------------------------------------------------------------- T-67

test('T-67  the five structural tags are not objects', () => {
	// One of each, and nothing that carries ink. A count of anything above zero
	// here means the drawing is being measured by the shape of its file.
	const structure = [
		'<svg xmlns="http://www.w3.org/2000/svg">',
		'<title>a</title>',
		'<desc>b</desc>',
		'<metadata>c</metadata>',
		'<defs></defs>',
		'</svg>'
	].join('\n');
	assert.equal(measureSvgWeight(structure).objects, 0);
});

test('T-67  but a mark inside <defs> is still a mark', () => {
	// The exclusion is by tag name, not by where the tag sits. `<defs>` itself
	// is not counted; the `<rect>` it holds is a drawn shape and is.
	const withDefs = '<svg><defs><pattern><rect /></pattern></defs><circle /></svg>';
	assert.equal(measureSvgWeight(withDefs).objects, 3); // pattern, rect, circle
});

test('T-67  and a closing tag is not a second object', () => {
	assert.equal(measureSvgWeight('<svg><rect></rect></svg>').objects, 1);
});

// ------------------------------------------------------------------- T-68

test('T-68  points come from the `points` attribute', () => {
	const onlyPoints = '<svg><polyline points="0,0 1,1 2,2" /></svg>';
	const weight = measureSvgWeight(onlyPoints);
	assert.equal(weight.points, 3);
	assert.equal(weight.objects, 1);
});

test('T-68  points come from the `d` attribute too', () => {
	// Six numbers, said in pairs, is three points.
	const onlyPath = '<svg><path d="M 0 0 L 10 10 L 20 0" /></svg>';
	const weight = measureSvgWeight(onlyPath);
	assert.equal(weight.points, 3);
	assert.equal(weight.objects, 1);
});

test('T-68  and a drawing holding both adds them, it does not pick one', () => {
	const both = '<svg><polyline points="0,0 1,1 2,2" /><path d="M 0 0 L 10 10 L 20 0" /></svg>';
	assert.equal(measureSvgWeight(both).points, 6);
});

test('T-68  an `id` is not read as a `d`', () => {
	// There is no word boundary between the `i` and the `d`, so `id="…"` must
	// contribute nothing. Without that guard every identifier in the file would
	// be counted as a path.
	assert.equal(measureSvgWeight('<svg><rect id="1 2 3 4" /></svg>').points, 0);
});

// ------------------------------------------------------------------- T-69

test('T-69  the drawer measures only when the work on screen has an SVG', () => {
	// The three cells share one derivation, and that derivation is null when
	// there is nothing to measure. Measuring an absent work would report zero,
	// and a zero here is a claim about a drawing that does not exist.
	assert.match(
		PANEL,
		/const detailSvgWeight = \$derived\(result\?\.svg \? measureSvgWeight\(result\.svg\) : null\)/,
		'the drawer measures without checking that there is an SVG'
	);
});

test('T-69  and all three cells fall back to a dash, never to a zero', () => {
	// Bytes go through formatByteSize, which answers '-' for null and now lives
	// in $lib/formatNumber (the canvas strip says the same number); the two
	// other cells check the derivation itself, since a formatter that groups
	// digits always returns a string and can no longer carry the dash.
	assert.match(PANEL, /formatByteSize\(detailSvgBytes\)/);
	assert.match(read('./formatNumber.ts'), /if \(bytes == null\) return '-';/);
	for (const field of ['objects', 'points']) {
		assert.match(
			PANEL,
			new RegExp(`\\{detailSvgWeight \\? groupDigits\\(detailSvgWeight\\.${field}\\) : '-'\\}`),
			`the ${field} cell does not fall back to a dash`
		);
	}
});

test('T-69  and it reads the result, not the history item', () => {
	// HistoryItem carries no `svg`, so `statusHistoryItem?.x ?? result?.x` -- the
	// shape every other detail row uses -- would have a left side that is always
	// undefined. These three read `result` directly, on purpose.
	assert.doesNotMatch(PANEL, /statusHistoryItem\?\.svg/);
});

// ------------------------------------------------------------------- T-70

test('T-70  the two new hint keys stand in all three i18n faces', () => {
	const ja = read('./i18n/ja.ts');
	const en = read('./i18n/en.ts');
	const types = read('./i18n/types.ts');
	for (const key of ['provenanceHintSvgObjects', 'provenanceHintSvgPoints']) {
		assert.match(ja, new RegExp(`\\n\\t${key}: '`), `ja.ts has no ${key}`);
		assert.match(en, new RegExp(`\\n\\t${key}: '`), `en.ts has no ${key}`);
		assert.match(types, new RegExp(`\\n\\t${key}: string;`), `types.ts has no ${key}`);
		assert.match(PANEL, new RegExp(`t\\(\\)\\.${key}`), `the drawer never uses ${key}`);
	}
});

test('T-70  and the two labels are the words the glossary settles on', () => {
	// Japanese is the source; the English side is the row added to GLOSSARY.md.
	assert.match(PANEL, /isJapanese \? 'SVG オブジェクト数' : 'SVG objects'/);
	assert.match(PANEL, /isJapanese \? 'SVG 点数' : 'SVG points'/);
	const glossary = read('./i18n/GLOSSARY.md');
	assert.match(glossary, /SVG オブジェクト数/, 'GLOSSARY.md does not settle the pair');
	assert.match(glossary, /\*\*SVG objects\*\*/);
	assert.match(glossary, /\*\*SVG points\*\*/);
});

// ------------------------------------------------------------------- T-71

test('T-71  one known drawing, and all three numbers agree with svg_weight.py', () => {
	// Not counted by hand. These are what `measure()` in
	// no-git-sync/scripts/svg_weight.py returns for the FIXTURE string above,
	// measured on 2026-08-15 against that exact text:
	//
	//   bytes=702 objects=10 points=14
	//   tags={'pattern': 1, 'rect': 2, 'g': 1, 'circle': 1, 'path': 2,
	//         'polyline': 2, 'polygon': 1}
	//
	// If this test goes red, one of the two halves of the pair has moved and
	// the other has not. Do not re-fit the number here; re-run the script.
	assert.deepEqual(measureSvgWeight(FIXTURE), { bytes: 702, objects: 10, points: 14 });
});

test('T-71  and the drawer shows that measurement, not a second one of its own', () => {
	// The point of the pair is defeated the moment the screen counts by itself.
	assert.match(PANEL, /import \{ measureSvgWeight \} from '\$lib\/svgWeight'/);
	assert.match(PANEL, /const detailSvgBytes = \$derived\(detailSvgWeight\?\.bytes \?\? null\)/);
	// The old inline byte count is gone, so bytes and the two new numbers come
	// from one function applied to one string.
	assert.doesNotMatch(PANEL, /new TextEncoder\(\)\.encode\(result\.svg\)/);
});
